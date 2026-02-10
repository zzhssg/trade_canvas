from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from fastapi import WebSocket

from ..ws_hub import CandleHub
from ..ws_protocol import (
    WS_ERR_BAD_REQUEST,
    WS_ERR_CAPACITY,
    WS_ERR_MSG_INVALID_ENVELOPE,
    WS_ERR_MSG_INVALID_SINCE,
    WS_ERR_MSG_INVALID_SUPPORTS_BATCH,
    WS_ERR_MSG_MISSING_SERIES_ID,
    WS_ERR_MSG_MISSING_TYPE,
    WS_ERR_MSG_ONDEMAND_CAPACITY,
    WS_MSG_ERROR,
    ws_err_msg_unknown_type,
)
from .contracts import CatchupReadRequest, MarketDataOrchestrator, WsCatchupRequest, WsEmitRequest, WsSubscribeCommand

logger = logging.getLogger(__name__)


def build_ws_error_payload(
    *,
    code: str,
    message: str,
    series_id: str | None = None,
) -> dict:
    payload = {"type": WS_MSG_ERROR, "code": code, "message": message}
    if series_id is not None:
        payload["series_id"] = series_id
    return payload


class WsMessageParser:
    @staticmethod
    def bad_request(*, message: str) -> dict:
        return build_ws_error_payload(code=WS_ERR_BAD_REQUEST, message=message)

    def parse_message_type(self, msg: object) -> str:
        if not isinstance(msg, dict):
            raise ValueError(WS_ERR_MSG_INVALID_ENVELOPE)
        msg_type = msg.get("type")
        if not isinstance(msg_type, str) or not msg_type:
            raise ValueError(WS_ERR_MSG_MISSING_TYPE)
        return msg_type

    def unknown_message_type(self, *, msg_type: str) -> dict:
        return self.bad_request(message=ws_err_msg_unknown_type(msg_type=msg_type))

    def parse_subscribe(self, msg: dict) -> WsSubscribeCommand:
        series_id = msg.get("series_id")
        if not isinstance(series_id, str) or not series_id:
            raise ValueError(WS_ERR_MSG_MISSING_SERIES_ID)

        since = msg.get("since")
        if since is not None and not isinstance(since, int):
            raise ValueError(WS_ERR_MSG_INVALID_SINCE)

        supports_batch = msg.get("supports_batch")
        if supports_batch is not None and not isinstance(supports_batch, bool):
            raise ValueError(WS_ERR_MSG_INVALID_SUPPORTS_BATCH)

        return WsSubscribeCommand(
            series_id=series_id,
            since=since,
            supports_batch=bool(supports_batch),
        )

    def parse_unsubscribe_series_id(self, msg: dict) -> str | None:
        series_id = msg.get("series_id")
        if not isinstance(series_id, str) or not series_id:
            return None
        return series_id


class WsSubscriptionCoordinator:
    def __init__(
        self,
        *,
        hub: CandleHub,
        ondemand_subscribe: Callable[[str], Awaitable[bool]] | None = None,
        ondemand_unsubscribe: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._hub = hub
        self._ondemand_subscribe = ondemand_subscribe
        self._ondemand_unsubscribe = ondemand_unsubscribe
        self._state_lock = asyncio.Lock()
        self._local_subscribed_by_ws: dict[WebSocket, set[str]] = {}

    async def _remember(self, *, ws: WebSocket, series_id: str) -> None:
        async with self._state_lock:
            self._local_subscribed_by_ws.setdefault(ws, set()).add(series_id)

    async def _forget(self, *, ws: WebSocket, series_id: str) -> None:
        async with self._state_lock:
            series = self._local_subscribed_by_ws.get(ws)
            if not series:
                return
            series.discard(series_id)
            if not series:
                self._local_subscribed_by_ws.pop(ws, None)

    async def _pop_local(self, *, ws: WebSocket) -> set[str]:
        async with self._state_lock:
            series = self._local_subscribed_by_ws.pop(ws, set())
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
        if ondemand_enabled:
            if self._ondemand_subscribe is None:
                return build_ws_error_payload(
                    code=WS_ERR_CAPACITY,
                    message=WS_ERR_MSG_ONDEMAND_CAPACITY,
                    series_id=series_id,
                )
            ok = await self._ondemand_subscribe(series_id)
            if not ok:
                return build_ws_error_payload(
                    code=WS_ERR_CAPACITY,
                    message=WS_ERR_MSG_ONDEMAND_CAPACITY,
                    series_id=series_id,
                )
        await self._hub.subscribe(ws, series_id=series_id, since=since, supports_batch=bool(supports_batch))
        await self._remember(ws=ws, series_id=series_id)
        return None

    async def handle_subscribe(
        self,
        *,
        ws: WebSocket,
        series_id: str,
        since: int | None,
        supports_batch: bool,
        ondemand_enabled: bool,
        market_data: MarketDataOrchestrator,
        derived_initial_backfill: Callable[..., Awaitable[None]],
        catchup_limit: int = 5000,
    ) -> tuple[dict | None, list[dict]]:
        started_at = time.perf_counter()
        await derived_initial_backfill(series_id=series_id)
        err_payload = await self.subscribe(
            ws=ws,
            series_id=series_id,
            since=since,
            supports_batch=bool(supports_batch),
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

        read_result = market_data.read_candles(
            CatchupReadRequest(
                series_id=series_id,
                since=since,
                limit=int(catchup_limit),
            )
        )
        current_last = await self._hub.get_last_sent(ws, series_id=series_id)
        catchup_result = await market_data.build_ws_catchup(
            WsCatchupRequest(
                series_id=series_id,
                since=since,
                last_sent=current_last,
                limit=int(catchup_limit),
                candles=read_result.candles,
            )
        )
        emit_result = market_data.build_ws_emit(
            WsEmitRequest(
                series_id=series_id,
                supports_batch=bool(supports_batch),
                catchup=catchup_result.candles,
                gap_payload=catchup_result.gap_payload,
            )
        )
        if emit_result.last_sent_time is not None:
            await self._hub.set_last_sent(ws, series_id=series_id, candle_time=int(emit_result.last_sent_time))
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        logger.info(
            "market_ws_subscribe_handled series_id=%s since=%s supports_batch=%s read_count=%s catchup_count=%s payload_count=%s gap_emitted=%s last_sent=%s elapsed_ms=%.2f",
            series_id,
            since,
            bool(supports_batch),
            len(read_result.candles),
            len(catchup_result.candles),
            len(emit_result.payloads),
            bool(catchup_result.gap_payload),
            emit_result.last_sent_time,
            elapsed_ms,
        )
        return None, emit_result.payloads

    async def unsubscribe(
        self,
        *,
        ws: WebSocket,
        series_id: str,
        ondemand_enabled: bool,
    ) -> None:
        if ondemand_enabled and self._ondemand_unsubscribe is not None:
            await self._ondemand_unsubscribe(series_id)
        await self._hub.unsubscribe(ws, series_id=series_id)
        await self._forget(ws=ws, series_id=series_id)

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
        if not ondemand_enabled or self._ondemand_unsubscribe is None:
            return
        for series_id in set(local_series) | set(hub_series):
            try:
                await self._ondemand_unsubscribe(series_id)
            except Exception:
                pass
