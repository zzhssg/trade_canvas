from __future__ import annotations

import time

from .debug_hub import DebugHub
from .pipelines import IngestPipeline, IngestPipelineError
from .runtime_metrics import RuntimeMetrics
from .schemas import (
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandlesClosedBatchRequest,
    IngestCandlesClosedBatchResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
)
from .service_errors import ServiceError
from .ws_hub import CandleHub


class MarketIngestService:
    def __init__(
        self,
        *,
        hub: CandleHub,
        debug_hub: DebugHub,
        ingest_pipeline: IngestPipeline,
        debug_api_enabled: bool,
        runtime_metrics: RuntimeMetrics | None = None,
    ) -> None:
        self._hub = hub
        self._debug_hub = debug_hub
        self._ingest_pipeline = ingest_pipeline
        self._debug_api_enabled = bool(debug_api_enabled)
        self._runtime_metrics = runtime_metrics

    def _debug_enabled(self) -> bool:
        return bool(self._debug_api_enabled)

    def _metrics_incr(self, name: str, *, labels: dict[str, object] | None = None) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.incr(name, labels=labels)

    def _metrics_observe_ms(self, name: str, *, duration_ms: float, labels: dict[str, object] | None = None) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.observe_ms(name, duration_ms=duration_ms, labels=labels)

    def _metrics_set_gauge(self, name: str, *, value: float, labels: dict[str, object] | None = None) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.set_gauge(name, value=value, labels=labels)

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

        try:
            result = await self._ingest_pipeline.run(
                batches={req.series_id: [req.candle]},
                publish=True,
            )
        except IngestPipelineError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self._metrics_incr(
                "market_ingest_closed_requests_total",
                labels={"result": "error", "step": str(exc.step)},
            )
            self._metrics_observe_ms(
                "market_ingest_closed_duration_ms",
                duration_ms=duration_ms,
                labels={"result": "error"},
            )
            if self._debug_enabled():
                self._debug_hub.emit(
                    pipe="write",
                    event="write.http.ingest_candle_closed_error",
                    series_id=req.series_id,
                    level="error",
                    message="ingest candle_closed failed",
                    data={
                        "step": str(exc.step),
                        "series_id": str(exc.series_id),
                        "error": str(exc.cause),
                        "compensated": bool(exc.compensated),
                        "overlay_compensated": bool(exc.overlay_compensated),
                        "candle_compensated_rows": int(exc.candle_compensated_rows),
                        "compensation_error": None if exc.compensation_error is None else str(exc.compensation_error),
                    },
                )
            raise ServiceError(
                status_code=500,
                detail=f"ingest_pipeline_failed:{exc.step}:{exc.series_id}",
                code="market.ingest_pipeline_failed",
            ) from exc
        factor_rebuilt = bool(req.series_id in set(result.rebuilt_series))
        duration_ms = (time.perf_counter() - t0) * 1000.0
        self._metrics_incr(
            "market_ingest_closed_requests_total",
            labels={"result": "ok"},
        )
        self._metrics_observe_ms(
            "market_ingest_closed_duration_ms",
            duration_ms=duration_ms,
            labels={"result": "ok"},
        )
        self._metrics_set_gauge(
            "market_ingest_last_candle_time",
            value=float(req.candle.candle_time),
            labels={"series_id": req.series_id},
        )
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
                    "duration_ms": int(duration_ms),
                },
            )

        return IngestCandleClosedResponse(
            ok=True,
            series_id=req.series_id,
            candle_time=req.candle.candle_time,
        )

    async def ingest_candles_closed_batch(
        self,
        req: IngestCandlesClosedBatchRequest,
    ) -> IngestCandlesClosedBatchResponse:
        t0 = time.perf_counter()
        count = int(len(req.candles))
        if self._debug_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candles_closed_batch_start",
                series_id=req.series_id,
                message="ingest candles_closed batch start",
                data={
                    "count": int(count),
                    "publish_ws": bool(req.publish_ws),
                },
            )

        try:
            result = await self._ingest_pipeline.run(
                batches={req.series_id: list(req.candles)},
                publish=bool(req.publish_ws),
            )
        except IngestPipelineError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self._metrics_incr(
                "market_ingest_closed_batch_requests_total",
                labels={"result": "error", "step": str(exc.step)},
            )
            self._metrics_observe_ms(
                "market_ingest_closed_batch_duration_ms",
                duration_ms=duration_ms,
                labels={"result": "error"},
            )
            if self._debug_enabled():
                self._debug_hub.emit(
                    pipe="write",
                    event="write.http.ingest_candles_closed_batch_error",
                    series_id=req.series_id,
                    level="error",
                    message="ingest candles_closed batch failed",
                    data={
                        "step": str(exc.step),
                        "series_id": str(exc.series_id),
                        "error": str(exc.cause),
                        "compensated": bool(exc.compensated),
                        "overlay_compensated": bool(exc.overlay_compensated),
                        "candle_compensated_rows": int(exc.candle_compensated_rows),
                        "compensation_error": None if exc.compensation_error is None else str(exc.compensation_error),
                    },
                )
            raise ServiceError(
                status_code=500,
                detail=f"ingest_pipeline_failed:{exc.step}:{exc.series_id}",
                code="market.ingest_pipeline_failed",
            ) from exc

        duration_ms = (time.perf_counter() - t0) * 1000.0
        self._metrics_incr(
            "market_ingest_closed_batch_requests_total",
            labels={"result": "ok"},
        )
        self._metrics_observe_ms(
            "market_ingest_closed_batch_duration_ms",
            duration_ms=duration_ms,
            labels={"result": "ok"},
        )

        first_time: int | None = None
        last_time: int | None = None
        if count > 0:
            ordered_times = sorted(int(candle.candle_time) for candle in req.candles)
            first_time = int(ordered_times[0])
            last_time = int(ordered_times[-1])
            self._metrics_set_gauge(
                "market_ingest_last_candle_time",
                value=float(last_time),
                labels={"series_id": req.series_id},
            )
        if self._debug_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candles_closed_batch_done",
                series_id=req.series_id,
                message="ingest candles_closed batch done",
                data={
                    "count": int(count),
                    "first_candle_time": None if first_time is None else int(first_time),
                    "last_candle_time": None if last_time is None else int(last_time),
                    "pipeline_duration_ms": int(result.duration_ms),
                    "duration_ms": int(duration_ms),
                    "publish_ws": bool(req.publish_ws),
                },
            )

        return IngestCandlesClosedBatchResponse(
            ok=True,
            series_id=req.series_id,
            count=int(count),
            first_candle_time=None if first_time is None else int(first_time),
            last_candle_time=None if last_time is None else int(last_time),
        )

    async def ingest_candle_forming(self, req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
        await self._hub.publish_forming(series_id=req.series_id, candle=req.candle)
        return IngestCandleFormingResponse(
            ok=True,
            series_id=req.series_id,
            candle_time=req.candle.candle_time,
        )
