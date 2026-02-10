from __future__ import annotations

import time

from .blocking import run_blocking
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .market_flags import debug_api_enabled
from .overlay_orchestrator import OverlayOrchestrator
from .schemas import (
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
)
from .store import CandleStore
from .ws_hub import CandleHub


class MarketIngestService:
    def __init__(
        self,
        *,
        store: CandleStore,
        factor_orchestrator: FactorOrchestrator,
        overlay_orchestrator: OverlayOrchestrator,
        hub: CandleHub,
        debug_hub: DebugHub,
    ) -> None:
        self._store = store
        self._factor_orchestrator = factor_orchestrator
        self._overlay_orchestrator = overlay_orchestrator
        self._hub = hub
        self._debug_hub = debug_hub

    async def ingest_candle_closed(self, req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
        t0 = time.perf_counter()
        if debug_api_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_start",
                series_id=req.series_id,
                message="ingest candle_closed start",
                data={"candle_time": int(req.candle.candle_time)},
            )

        steps: list[dict] = []
        factor_rebuilt = {"value": False}

        def _persist_and_sidecars() -> None:
            t_step = time.perf_counter()
            self._store.upsert_closed(req.series_id, req.candle)
            steps.append(
                {
                    "name": "store.upsert_closed",
                    "ok": True,
                    "duration_ms": int((time.perf_counter() - t_step) * 1000),
                }
            )

            try:
                t_step = time.perf_counter()
                factor_result = self._factor_orchestrator.ingest_closed(
                    series_id=req.series_id,
                    up_to_candle_time=req.candle.candle_time,
                )
                factor_rebuilt["value"] = bool(getattr(factor_result, "rebuilt", False))
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

            try:
                t_step = time.perf_counter()
                if factor_rebuilt["value"]:
                    self._overlay_orchestrator.reset_series(series_id=req.series_id)
                self._overlay_orchestrator.ingest_closed(
                    series_id=req.series_id,
                    up_to_candle_time=req.candle.candle_time,
                )
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

        await run_blocking(_persist_and_sidecars)
        await self._hub.publish_closed(series_id=req.series_id, candle=req.candle)
        if factor_rebuilt["value"]:
            await self._hub.publish_system(
                series_id=req.series_id,
                event="factor.rebuild",
                message="因子口径更新，已自动完成历史重算",
                data={"series_id": req.series_id},
            )

        if debug_api_enabled():
            self._debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_done",
                series_id=req.series_id,
                message="ingest candle_closed done",
                data={
                    "candle_time": int(req.candle.candle_time),
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
