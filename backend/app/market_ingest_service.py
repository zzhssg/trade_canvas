from __future__ import annotations

import time

from .debug_hub import DebugHub
from .flags import resolve_env_bool
from .pipelines import IngestPipeline
from .schemas import (
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
)
from .ws_hub import CandleHub


class MarketIngestService:
    def __init__(
        self,
        *,
        hub: CandleHub,
        debug_hub: DebugHub,
        ingest_pipeline: IngestPipeline,
    ) -> None:
        self._hub = hub
        self._debug_hub = debug_hub
        self._ingest_pipeline = ingest_pipeline

    def _debug_enabled(self) -> bool:
        return resolve_env_bool("TRADE_CANVAS_ENABLE_DEBUG_API", fallback=False)

    async def ingest_candle_closed(self, req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
        t0 = time.perf_counter()
        if self._debug_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_start",
                series_id=req.series_id,
                message="ingest candle_closed start",
                data={"candle_time": int(req.candle.candle_time)},
            )

        result = await self._ingest_pipeline.run(
            batches={req.series_id: [req.candle]},
            publish=True,
        )
        factor_rebuilt = bool(req.series_id in set(result.rebuilt_series))
        steps = [
            {
                "name": str(step.name),
                "ok": bool(step.ok),
                "duration_ms": int(step.duration_ms),
            }
            for step in result.steps
        ]

        if self._debug_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_done",
                series_id=req.series_id,
                message="ingest candle_closed done",
                data={
                    "candle_time": int(req.candle.candle_time),
                    "factor_rebuilt": bool(factor_rebuilt),
                    "pipeline_duration_ms": int(result.duration_ms),
                    "steps": list(steps),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )

        return IngestCandleClosedResponse(
            ok=True,
            series_id=req.series_id,
            candle_time=req.candle.candle_time,
        )

    async def ingest_candle_forming(self, req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
        await self._hub.publish_forming(series_id=req.series_id, candle=req.candle)
        return IngestCandleFormingResponse(
            ok=True,
            series_id=req.series_id,
            candle_time=req.candle.candle_time,
        )
