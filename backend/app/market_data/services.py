from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable

from fastapi import WebSocket

from ..blocking import run_blocking
from ..derived_timeframes import (
    derived_base_timeframe,
    derived_enabled,
    is_derived_series_id,
    rollup_closed_candles,
    to_base_series_id,
)
from ..history_bootstrapper import backfill_tail_from_freqtrade
from ..market_backfill import backfill_market_gap_best_effort
from ..market_backfill import backfill_from_ccxt_range
from ..pipelines import IngestPipeline
from ..series_id import parse_series_id
from ..schemas import CandleClosed
from ..store import CandleStore
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from ..ws_hub import CandleHub
from .contracts import (
    BackfillGapRequest,
    BackfillGapResult,
    BackfillService,
    CatchupReadRequest,
    CatchupReadResult,
    CandleReadService,
    FreshnessService,
    FreshnessSnapshot,
    FreshnessState,
    MarketDataOrchestrator,
    WsCatchupRequest,
    WsEmitRequest,
    WsEmitResult,
    WsSubscribeCommand,
    WsDeliveryService,
)
from ..ws_protocol import (
    WS_ERR_BAD_REQUEST,
    WS_ERR_CAPACITY,
    WS_ERR_MSG_INVALID_ENVELOPE,
    WS_ERR_MSG_INVALID_SINCE,
    WS_ERR_MSG_INVALID_SUPPORTS_BATCH,
    WS_ERR_MSG_MISSING_SERIES_ID,
    WS_ERR_MSG_MISSING_TYPE,
    WS_ERR_MSG_ONDEMAND_CAPACITY,
    WS_MSG_CANDLE_CLOSED,
    WS_MSG_CANDLES_BATCH,
    WS_MSG_ERROR,
    ws_err_msg_unknown_type,
)

logger = logging.getLogger(__name__)


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


class StoreCandleReadService(CandleReadService):
    def __init__(self, *, store: CandleStore) -> None:
        self._store = store

    def read_tail(self, *, series_id: str, limit: int) -> list[CandleClosed]:
        return self._store.get_closed(series_id, since=None, limit=int(limit))

    def read_incremental(self, *, series_id: str, since: int, limit: int) -> list[CandleClosed]:
        return self._store.get_closed(series_id, since=int(since), limit=int(limit))

    def read_between(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[CandleClosed]:
        return self._store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(end_time),
            limit=int(limit),
        )


class StoreBackfillService(BackfillService):
    def __init__(
        self,
        *,
        store: CandleStore,
        gap_backfill_fn: Callable[..., int] = backfill_market_gap_best_effort,
        tail_backfill_fn: Callable[..., int] = backfill_tail_from_freqtrade,
    ) -> None:
        self._store = store
        self._gap_backfill_fn = gap_backfill_fn
        self._tail_backfill_fn = tail_backfill_fn

    def backfill_gap(self, req: BackfillGapRequest) -> BackfillGapResult:
        filled = int(
            self._gap_backfill_fn(
                store=self._store,
                series_id=req.series_id,
                expected_next_time=int(req.expected_next_time),
                actual_time=int(req.actual_time),
            )
        )
        return BackfillGapResult(
            series_id=req.series_id,
            expected_next_time=int(req.expected_next_time),
            actual_time=int(req.actual_time),
            filled_count=max(0, filled),
        )

    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int:
        target = int(target_candles)
        if target <= 0:
            return 0
        filled = max(0, int(self._tail_backfill_fn(self._store, series_id=series_id, limit=target)))

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        if to_time is None:
            head = self._store.head_time(series_id)
            if head is not None:
                end_time = int(head)
            else:
                now = int(time.time())
                end_time = int(now // int(tf_s)) * int(tf_s)
        else:
            end_time = int(to_time)
        start_time = max(0, int(end_time) - (int(target) - 1) * int(tf_s))

        count_after_tail = self._store.count_closed_between_times(series_id, start_time=start_time, end_time=end_time)
        if int(count_after_tail) < int(target) and _truthy_flag(os.environ.get("TRADE_CANVAS_ENABLE_CCXT_BACKFILL")):
            try:
                backfill_from_ccxt_range(
                    candle_store=self._store,
                    series_id=series_id,
                    start_time=int(start_time),
                    end_time=int(end_time),
                )
            except Exception:
                pass

        if to_time is None:
            if head is None:
                head_after = self._store.head_time(series_id)
                if head_after is None:
                    return filled
                end_time = int(head_after)
                start_time = max(0, int(end_time) - (int(target) - 1) * int(tf_s))
            covered = self._store.count_closed_between_times(series_id, start_time=start_time, end_time=end_time)
            return max(int(filled), int(covered))
        return self._store.count_closed_between_times(series_id, start_time=start_time, end_time=end_time)


class StoreFreshnessService(FreshnessService):
    def __init__(
        self,
        *,
        store: CandleStore,
        fresh_window_candles: int = 2,
        stale_window_candles: int = 5,
        now_fn: Callable[[], int] | None = None,
    ) -> None:
        self._store = store
        self._fresh_window_candles = max(1, int(fresh_window_candles))
        self._stale_window_candles = max(self._fresh_window_candles + 1, int(stale_window_candles))
        self._now_fn = now_fn or (lambda: int(time.time()))

    @staticmethod
    def _resolve_timeframe_seconds(series_id: str) -> int | None:
        try:
            timeframe = parse_series_id(series_id).timeframe
            return int(timeframe_to_seconds(timeframe))
        except Exception:
            return None

    def snapshot(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot:
        now = int(now_time) if now_time is not None else int(self._now_fn())
        head_time = self._store.head_time(series_id)
        if head_time is None:
            return FreshnessSnapshot(
                series_id=series_id,
                head_time=None,
                now_time=now,
                lag_seconds=None,
                state="missing",
            )

        lag = max(0, int(now) - int(head_time))
        tf_s = self._resolve_timeframe_seconds(series_id)
        state: FreshnessState
        if tf_s is None or tf_s <= 0:
            state = "degraded"
        else:
            fresh_lag_max = int(tf_s) * int(self._fresh_window_candles)
            stale_lag_max = int(tf_s) * int(self._stale_window_candles)
            if lag <= fresh_lag_max:
                state = "fresh"
            elif lag <= stale_lag_max:
                state = "stale"
            else:
                state = "degraded"

        return FreshnessSnapshot(
            series_id=series_id,
            head_time=int(head_time),
            now_time=now,
            lag_seconds=lag,
            state=state,
        )


class HubWsDeliveryService(WsDeliveryService):
    def __init__(self, *, hub: CandleHub) -> None:
        self._hub = hub

    async def heal_catchup_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        return await self._hub.heal_catchup_gap(
            series_id=series_id,
            effective_since=effective_since,
            catchup=catchup,
        )


class DefaultMarketDataOrchestrator(MarketDataOrchestrator):
    def __init__(
        self,
        *,
        reader: CandleReadService,
        freshness: FreshnessService,
        ws_delivery: WsDeliveryService,
    ) -> None:
        self._reader = reader
        self._freshness = freshness
        self._ws_delivery = ws_delivery

    def freshness(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot:
        return self._freshness.snapshot(series_id=series_id, now_time=now_time)

    def read_candles(self, req: CatchupReadRequest) -> CatchupReadResult:
        if req.since is None:
            candles = self._reader.read_tail(series_id=req.series_id, limit=req.limit)
        else:
            candles = self._reader.read_incremental(series_id=req.series_id, since=req.since, limit=req.limit)
        return CatchupReadResult(
            series_id=req.series_id,
            effective_since=req.since,
            candles=candles,
            gap_payload=None,
        )

    async def build_ws_catchup(self, req: WsCatchupRequest) -> CatchupReadResult:
        if req.candles is None:
            out = self.read_candles(
                CatchupReadRequest(
                    series_id=req.series_id,
                    since=req.since,
                    limit=req.limit,
                )
            )
            catchup = out.candles
        else:
            catchup = req.candles
        effective_since = req.since
        if req.since is not None:
            if req.last_sent is not None and int(req.last_sent) > int(req.since):
                effective_since = int(req.last_sent)
            if effective_since is not None and catchup:
                catchup = [c for c in catchup if int(c.candle_time) > int(effective_since)]
        healed, gap_payload = await self.heal_ws_gap(
            series_id=req.series_id,
            effective_since=effective_since,
            catchup=catchup,
        )
        return CatchupReadResult(
            series_id=req.series_id,
            effective_since=effective_since,
            candles=healed,
            gap_payload=gap_payload,
        )

    def build_ws_emit(self, req: WsEmitRequest) -> WsEmitResult:
        payloads: list[dict] = []
        if req.gap_payload is not None:
            payloads.append(req.gap_payload)

        last_sent_time: int | None = None
        if req.supports_batch:
            if req.catchup:
                payloads.append(
                    {
                        "type": WS_MSG_CANDLES_BATCH,
                        "series_id": req.series_id,
                        "candles": [c.model_dump() for c in req.catchup],
                    }
                )
                last_sent_time = int(req.catchup[-1].candle_time)
            return WsEmitResult(payloads=payloads, last_sent_time=last_sent_time)

        for candle in req.catchup:
            payloads.append(
                {
                    "type": WS_MSG_CANDLE_CLOSED,
                    "series_id": req.series_id,
                    "candle": candle.model_dump(),
                }
            )
            last_sent_time = int(candle.candle_time)
        return WsEmitResult(payloads=payloads, last_sent_time=last_sent_time)

    async def heal_ws_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        return await self._ws_delivery.heal_catchup_gap(
            series_id=series_id,
            effective_since=effective_since,
            catchup=catchup,
        )


def build_gap_backfill_handler(
    *,
    reader: CandleReadService,
    backfill: BackfillService,
    enabled_env: str = "TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL",
    read_limit: int = 5000,
):
    async def _handler(series_id: str, expected_next_time: int, actual_time: int) -> list[CandleClosed]:
        if os.environ.get(enabled_env) != "1":
            return []

        res = await run_blocking(
            backfill.backfill_gap,
            BackfillGapRequest(
                series_id=series_id,
                expected_next_time=int(expected_next_time),
                actual_time=int(actual_time),
            ),
        )
        if int(res.filled_count) <= 0:
            return []

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        end_time = int(actual_time) - int(tf_s)
        if end_time < int(expected_next_time):
            return []
        return await run_blocking(
            reader.read_between,
            series_id=series_id,
            start_time=int(expected_next_time),
            end_time=int(end_time),
            limit=int(read_limit),
        )

    return _handler


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


def build_derived_initial_backfill_handler(
    *,
    store: CandleStore,
    factor_orchestrator,
    overlay_orchestrator,
    ingest_pipeline: IngestPipeline | None = None,
    enable_ingest_pipeline_v2: bool = False,
):
    async def _handler(*, series_id: str) -> None:
        if not derived_enabled() or not is_derived_series_id(series_id):
            return
        try:
            await run_blocking(_backfill_once, series_id)
        except Exception:
            return

    def _backfill_once(series_id: str) -> None:
        if store.head_time(series_id) is not None:
            return
        base_series_id = to_base_series_id(series_id)
        limit_raw = (os.environ.get("TRADE_CANVAS_DERIVED_BACKFILL_BASE_CANDLES") or "").strip()
        try:
            base_limit = max(100, int(limit_raw)) if limit_raw else 2000
        except ValueError:
            base_limit = 2000

        base_candles = store.get_closed(base_series_id, since=None, limit=int(base_limit))
        if not base_candles:
            return
        derived_tf = parse_series_id(series_id).timeframe
        derived_closed = rollup_closed_candles(
            base_timeframe=derived_base_timeframe(),
            derived_timeframe=derived_tf,
            base_candles=base_candles,
        )
        if not derived_closed:
            return

        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, series_id, derived_closed)
            conn.commit()

        if bool(enable_ingest_pipeline_v2) and ingest_pipeline is not None:
            ingest_pipeline.refresh_series_sync(
                up_to_times={series_id: int(derived_closed[-1].candle_time)},
            )
            return

        rebuilt = False
        try:
            factor_result = factor_orchestrator.ingest_closed(
                series_id=series_id,
                up_to_candle_time=int(derived_closed[-1].candle_time),
            )
            rebuilt = bool(getattr(factor_result, "rebuilt", False))
        except Exception:
            pass
        try:
            if rebuilt:
                overlay_orchestrator.reset_series(series_id=series_id)
            overlay_orchestrator.ingest_closed(
                series_id=series_id,
                up_to_candle_time=int(derived_closed[-1].candle_time),
            )
        except Exception:
            pass

    return _handler
