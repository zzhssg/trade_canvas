from __future__ import annotations

from dataclasses import dataclass

from .debug_hub import DebugHub
from .factor_store import FactorStore
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .schemas import ReplayPrepareRequestV1, ReplayPrepareResponseV1
from .service_errors import ServiceError
from .store import CandleStore


@dataclass(frozen=True)
class ReplayPrepareService:
    store: CandleStore
    factor_store: FactorStore
    overlay_store: OverlayStore
    ingest_pipeline: IngestPipeline
    debug_hub: DebugHub
    debug_api_enabled: bool = False

    def _require_aligned_time(self, *, series_id: str, to_time: int | None) -> tuple[int, int]:
        store_head = self.store.head_time(series_id)
        if store_head is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay_prepare.no_data")
        requested_time = int(to_time) if to_time is not None else int(store_head)
        aligned = self.store.floor_time(series_id, at_time=int(requested_time))
        if aligned is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay_prepare.no_data")
        return int(requested_time), int(aligned)

    @staticmethod
    def _clamp_window_candles(window_candles: int | None) -> int:
        value = int(window_candles or 2000)
        return min(5000, max(100, value))

    def prepare(self, payload: ReplayPrepareRequestV1) -> ReplayPrepareResponseV1:
        series_id = payload.series_id
        requested_time, aligned = self._require_aligned_time(series_id=series_id, to_time=payload.to_time)
        window_candles = self._clamp_window_candles(payload.window_candles)

        computed = False
        factor_head = self.factor_store.head_time(series_id)
        overlay_head = self.overlay_store.head_time(series_id)
        if (
            factor_head is None
            or int(factor_head) < int(aligned)
            or overlay_head is None
            or int(overlay_head) < int(aligned)
        ):
            pipeline_result = self.ingest_pipeline.refresh_series_sync(
                up_to_times={series_id: int(aligned)}
            )
            computed = bool(pipeline_result.steps)

        factor_head = self.factor_store.head_time(series_id)
        overlay_head = self.overlay_store.head_time(series_id)
        if factor_head is None or int(factor_head) < int(aligned):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:factor",
                code="replay_prepare.ledger_out_of_sync.factor",
            )
        if overlay_head is None or int(overlay_head) < int(aligned):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:overlay",
                code="replay_prepare.ledger_out_of_sync.overlay",
            )

        if bool(self.debug_api_enabled):
            self.debug_hub.emit(
                pipe="read",
                event="read.http.replay_prepare",
                series_id=series_id,
                message="prepare replay",
                data={
                    "requested_time": int(requested_time),
                    "aligned_time": int(aligned),
                    "window_candles": int(window_candles),
                    "factor_head_time": int(factor_head),
                    "overlay_head_time": int(overlay_head),
                    "computed": bool(computed),
                },
            )

        return ReplayPrepareResponseV1(
            ok=True,
            series_id=series_id,
            requested_time=int(requested_time),
            aligned_time=int(aligned),
            window_candles=int(window_candles),
            factor_head_time=int(factor_head) if factor_head is not None else None,
            overlay_head_time=int(overlay_head) if overlay_head is not None else None,
            computed=bool(computed),
        )
