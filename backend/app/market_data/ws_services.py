from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Mapping

from fastapi import WebSocket

from ..runtime.metrics import RuntimeMetrics
from ..ws.hub import CandleHub
from ..ws.protocol import (
    WS_ERR_CAPACITY,
    WS_ERR_MSG_ONDEMAND_CAPACITY,
)
from .contracts import MarketDataOrchestrator, WsHandleSubscribeRequest, WsSubscribeRequest
from .ws_message_parser import WsMessageParser, build_ws_error_payload

logger = logging.getLogger(__name__)


class WsSubscriptionCoordinator:
    def __init__(
        self,
        *,
        hub: CandleHub,
        ondemand_subscribe: Callable[[str], Awaitable[bool]] | None = None,
        ondemand_unsubscribe: Callable[[str], Awaitable[None]] | None = None,
        runtime_metrics: RuntimeMetrics | None = None,
    ) -> None:
        self._hub = hub
        self._ondemand_subscribe = ondemand_subscribe
        self._ondemand_unsubscribe = ondemand_unsubscribe
        self._runtime_metrics = runtime_metrics
        self._state_lock = asyncio.Lock()
        self._local_subscribed_by_ws: dict[WebSocket, set[str]] = {}

    def _metrics_incr(self, name: str, *, value: float = 1.0, labels: Mapping[str, object] | None = None) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.incr(name, value=value, labels=labels)

    def _metrics_observe_ms(
        self,
        name: str,
        *,
        duration_ms: float,
        labels: Mapping[str, object] | None = None,
    ) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.observe_ms(name, duration_ms=duration_ms, labels=labels)

    def _metrics_set_gauge(self, name: str, *, value: float, labels: Mapping[str, object] | None = None) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.set_gauge(name, value=value, labels=labels)

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return (time.perf_counter() - started_at) * 1000.0

    def _record_subscribe_result(self, *, result: str, started_at: float) -> None:
        labels = {"result": str(result)}
        self._metrics_incr("market_ws_subscribe_total", labels=labels)
        self._metrics_observe_ms(
            "market_ws_subscribe_duration_ms",
            duration_ms=self._elapsed_ms(started_at),
            labels=labels,
        )

    def _active_subscriptions_locked(self) -> int:
        return sum(len(series_ids) for series_ids in self._local_subscribed_by_ws.values())

    def _sync_active_subscriptions_gauge_locked(self) -> None:
        self._metrics_set_gauge(
            "market_ws_active_subscriptions",
            value=float(self._active_subscriptions_locked()),
        )

    async def _remember(self, *, ws: WebSocket, series_id: str) -> None:
        async with self._state_lock:
            self._local_subscribed_by_ws.setdefault(ws, set()).add(series_id)
            self._sync_active_subscriptions_gauge_locked()

    async def _is_subscribed(self, *, ws: WebSocket, series_id: str) -> bool:
        async with self._state_lock:
            series = self._local_subscribed_by_ws.get(ws)
            return bool(series and series_id in series)

    async def _forget(self, *, ws: WebSocket, series_id: str) -> None:
        async with self._state_lock:
            series = self._local_subscribed_by_ws.get(ws)
            if not series:
                return
            series.discard(series_id)
            if not series:
                self._local_subscribed_by_ws.pop(ws, None)
            self._sync_active_subscriptions_gauge_locked()

    async def _pop_local(self, *, ws: WebSocket) -> set[str]:
        async with self._state_lock:
            series = self._local_subscribed_by_ws.pop(ws, set())
            self._sync_active_subscriptions_gauge_locked()
        return set(series)

    async def subscribe(
        self,
        *,
        ws: WebSocket,
        series_id: str,
        since: int | None,
        supports_batch: bool,
        ondemand_enabled: bool,
    ) -> dict | None:
        started_at = time.perf_counter()
        already_subscribed = await self._is_subscribed(ws=ws, series_id=series_id)
        if ondemand_enabled and not already_subscribed:
            if self._ondemand_subscribe is None:
                self._record_subscribe_result(result="capacity", started_at=started_at)
                return build_ws_error_payload(
                    code=WS_ERR_CAPACITY,
                    message=WS_ERR_MSG_ONDEMAND_CAPACITY,
                    series_id=series_id,
                )
            ok = await self._ondemand_subscribe(series_id)
            if not ok:
                self._record_subscribe_result(result="capacity", started_at=started_at)
                return build_ws_error_payload(
                    code=WS_ERR_CAPACITY,
                    message=WS_ERR_MSG_ONDEMAND_CAPACITY,
                    series_id=series_id,
                )
        await self._hub.subscribe(ws, series_id=series_id, since=since, supports_batch=bool(supports_batch))
        await self._remember(ws=ws, series_id=series_id)
        self._record_subscribe_result(result="ok", started_at=started_at)
        return None

    async def handle_subscribe(
        self,
        *,
        ws: WebSocket,
        request: WsHandleSubscribeRequest,
        market_data: MarketDataOrchestrator,
        derived_initial_backfill: Callable[..., Awaitable[None]],
    ) -> tuple[dict | None, list[dict]]:
        series_id = str(request.series_id)
        since = request.since
        supports_batch = bool(request.supports_batch)
        ondemand_enabled = bool(request.ondemand_enabled)
        catchup_limit = int(request.catchup_limit)
        started_at = time.perf_counter()
        await derived_initial_backfill(series_id=series_id)
        err_payload = await self.subscribe(
            ws=ws,
            series_id=series_id,
            since=since,
            supports_batch=supports_batch,
            ondemand_enabled=ondemand_enabled,
        )
        if err_payload is not None:
            logger.warning(
                "market_ws_subscribe_rejected series_id=%s since=%s supports_batch=%s ondemand_enabled=%s reason=%s",
                series_id,
                since,
                bool(supports_batch),
                bool(ondemand_enabled),
                err_payload.get("message"),
            )
            return err_payload, []

        result = await market_data.build_ws_subscribe(
            WsSubscribeRequest(
                series_id=series_id,
                since=since,
                supports_batch=supports_batch,
                limit=int(catchup_limit),
                get_last_sent=lambda: self._hub.get_last_sent(ws, series_id=series_id),
            )
        )
        if result.last_sent_time is not None:
            await self._hub.set_last_sent(ws, series_id=series_id, candle_time=int(result.last_sent_time))
        catchup_count = int(result.catchup_count)
        payload_count = len(result.payloads)
        self._metrics_set_gauge(
            "market_ws_last_catchup_count",
            value=float(catchup_count),
        )
        self._metrics_set_gauge(
            "market_ws_last_payload_count",
            value=float(payload_count),
        )
        if catchup_count > 0:
            self._metrics_incr(
                "market_ws_catchup_candles_total",
                value=float(catchup_count),
            )
        if payload_count > 0:
            self._metrics_incr(
                "market_ws_payloads_total",
                value=float(payload_count),
            )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        logger.info(
            "market_ws_subscribe_handled series_id=%s since=%s supports_batch=%s read_count=%s catchup_count=%s payload_count=%s gap_emitted=%s last_sent=%s elapsed_ms=%.2f",
            series_id,
            since,
            bool(supports_batch),
            int(result.read_count),
            catchup_count,
            payload_count,
            bool(result.gap_emitted),
            result.last_sent_time,
            elapsed_ms,
        )
        return None, result.payloads

    async def unsubscribe(
        self,
        *,
        ws: WebSocket,
        series_id: str,
        ondemand_enabled: bool,
    ) -> None:
        started_at = time.perf_counter()
        subscribed = await self._is_subscribed(ws=ws, series_id=series_id)
        if ondemand_enabled and subscribed and self._ondemand_unsubscribe is not None:
            await self._ondemand_unsubscribe(series_id)
        await self._hub.unsubscribe(ws, series_id=series_id)
        await self._forget(ws=ws, series_id=series_id)
        result = "ok" if subscribed else "noop"
        labels = {"result": result}
        self._metrics_incr("market_ws_unsubscribe_total", labels=labels)
        self._metrics_observe_ms(
            "market_ws_unsubscribe_duration_ms",
            duration_ms=self._elapsed_ms(started_at),
            labels=labels,
        )

    async def cleanup_disconnect(
        self,
        *,
        ws: WebSocket,
        ondemand_enabled: bool,
    ) -> None:
        local_series = await self._pop_local(ws=ws)
        try:
            hub_series = await self._hub.pop_ws(ws)
        except Exception:
            hub_series = []
        series_to_cleanup = set(local_series) | set(hub_series)
        self._metrics_incr("market_ws_disconnect_cleanup_total")
        self._metrics_set_gauge(
            "market_ws_disconnect_cleanup_series_count",
            value=float(len(series_to_cleanup)),
        )
        if not ondemand_enabled or self._ondemand_unsubscribe is None:
            return
        for series_id in series_to_cleanup:
            try:
                await self._ondemand_unsubscribe(series_id)
                self._metrics_incr(
                    "market_ws_disconnect_unsubscribe_total",
                    labels={"result": "ok"},
                )
            except Exception:
                self._metrics_incr(
                    "market_ws_disconnect_unsubscribe_total",
                    labels={"result": "error"},
                )
