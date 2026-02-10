from __future__ import annotations

from ..blocking import run_blocking
from ..schemas import CandleClosed
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from ..ws_hub import CandleHub
from ..ws_protocol import WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLES_BATCH
from .contracts import (
    BackfillGapRequest,
    BackfillService,
    CatchupReadRequest,
    CatchupReadResult,
    CandleReadService,
    FreshnessService,
    FreshnessSnapshot,
    MarketDataOrchestrator,
    WsCatchupRequest,
    WsDeliveryService,
    WsEmitRequest,
    WsEmitResult,
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
