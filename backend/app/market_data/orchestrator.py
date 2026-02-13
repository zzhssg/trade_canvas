from __future__ import annotations

import time

from ..runtime.blocking import run_blocking
from ..core.schemas import CandleClosed
from ..core.timeframe import expected_latest_closed_time, series_id_timeframe, timeframe_to_seconds
from ..ws.hub import CandleHub
from ..ws.protocol import WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLES_BATCH
from .contracts import (
    BackfillGapRequest,
    BackfillService,
    CatchupReadRequest,
    CatchupReadResult,
    CandleReadService,
    FreshnessService,
    FreshnessSnapshot,
    MarketDataOrchestrator,
    WsDeliveryService,
    WsSubscribeRequest,
    WsSubscribeResult,
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

    def _latest_closed_time(self, *, series_id: str) -> int:
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        now = int(time.time())
        return expected_latest_closed_time(
            now_time=now,
            timeframe_seconds=int(tf_s),
        )

    @staticmethod
    def _is_plausible_closed_window(*, latest_candle_time: int, latest_closed_time: int, timeframe_seconds: int) -> bool:
        tf = max(1, int(timeframe_seconds))
        return int(latest_candle_time) <= int(latest_closed_time) + int(tf) * 2

    def _filter_ahead_candles(
        self,
        *,
        series_id: str,
        candles: list[CandleClosed],
    ) -> list[CandleClosed]:
        if not candles:
            return []
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        latest_closed_time = self._latest_closed_time(series_id=series_id)
        latest_candle_time = max(int(c.candle_time) for c in candles)
        if not self._is_plausible_closed_window(
            latest_candle_time=int(latest_candle_time),
            latest_closed_time=int(latest_closed_time),
            timeframe_seconds=int(tf_s),
        ):
            return list(candles)
        return [c for c in candles if int(c.candle_time) <= int(latest_closed_time)]

    def _clamp_since_to_latest_closed(self, *, series_id: str, since: int | None) -> int | None:
        if since is None:
            return None
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        latest_closed_time = self._latest_closed_time(series_id=series_id)
        if not self._is_plausible_closed_window(
            latest_candle_time=int(since),
            latest_closed_time=int(latest_closed_time),
            timeframe_seconds=int(tf_s),
        ):
            return int(since)
        return min(int(since), int(latest_closed_time))

    def freshness(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot:
        return self._freshness.snapshot(series_id=series_id, now_time=now_time)

    def read_candles(self, req: CatchupReadRequest) -> CatchupReadResult:
        since = self._clamp_since_to_latest_closed(
            series_id=req.series_id,
            since=req.since,
        )
        if since is None:
            candles = self._reader.read_tail(series_id=req.series_id, limit=req.limit)
        else:
            candles = self._reader.read_incremental(series_id=req.series_id, since=since, limit=req.limit)
        candles = self._filter_ahead_candles(
            series_id=req.series_id,
            candles=candles,
        )
        return CatchupReadResult(
            series_id=req.series_id,
            effective_since=since,
            candles=candles,
            gap_payload=None,
        )

    async def build_ws_subscribe(self, req: WsSubscribeRequest) -> WsSubscribeResult:
        read_result = self.read_candles(
            CatchupReadRequest(
                series_id=req.series_id,
                since=req.since,
                limit=req.limit,
            )
        )
        last_sent = await req.get_last_sent()
        if last_sent is not None:
            last_sent = self._clamp_since_to_latest_closed(
                series_id=req.series_id,
                since=int(last_sent),
            )
        effective_since = read_result.effective_since
        if effective_since is not None:
            effective_since = self._clamp_since_to_latest_closed(
                series_id=req.series_id,
                since=int(effective_since),
            )
        catchup = list(read_result.candles)
        if req.since is not None:
            if last_sent is not None and int(last_sent) > int(req.since):
                effective_since = int(last_sent)
            if effective_since is not None and catchup:
                catchup = [c for c in catchup if int(c.candle_time) > int(effective_since)]
        healed, gap_payload = await self._ws_delivery.heal_catchup_gap(
            series_id=req.series_id,
            effective_since=effective_since,
            catchup=catchup,
        )

        payloads: list[dict] = []
        if gap_payload is not None:
            payloads.append(gap_payload)

        last_sent_time: int | None = effective_since
        if bool(req.supports_batch):
            if healed:
                payloads.append(
                    {
                        "type": WS_MSG_CANDLES_BATCH,
                        "series_id": req.series_id,
                        "candles": [c.model_dump() for c in healed],
                    }
                )
                last_sent_time = int(healed[-1].candle_time)
        else:
            for candle in healed:
                payloads.append(
                    {
                        "type": WS_MSG_CANDLE_CLOSED,
                        "series_id": req.series_id,
                        "candle": candle.model_dump(),
                    }
                )
                last_sent_time = int(candle.candle_time)

        return WsSubscribeResult(
            series_id=req.series_id,
            effective_since=effective_since,
            read_count=len(read_result.candles),
            catchup_count=len(healed),
            payloads=payloads,
            last_sent_time=last_sent_time,
            gap_emitted=bool(gap_payload is not None),
        )


def build_gap_backfill_handler(
    *,
    reader: CandleReadService,
    backfill: BackfillService,
    read_limit: int = 5000,
    enabled: bool = False,
):
    async def _handler(series_id: str, expected_next_time: int, actual_time: int) -> list[CandleClosed]:
        if not bool(enabled):
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
