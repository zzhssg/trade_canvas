from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .ledger_alignment import require_aligned_point, require_ledger_heads_ready
from .ledger_sync_service import LedgerAlignedPoint, LedgerHeadTimes
from .schemas import ReplayPrepareRequestV1, ReplayPrepareResponseV1
from .shared_ports import AlignedStorePort, DebugHubPort, HeadStorePort, IngestPipelineSyncPort


class _LedgerSyncLike(Protocol):
    def resolve_aligned_point(
        self,
        *,
        series_id: str,
        to_time: int | None,
        no_data_code: str,
        no_data_detail: str = "no_data",
    ) -> LedgerAlignedPoint: ...

    def refresh_if_needed(self, *, series_id: str, up_to_time: int): ...

    def require_heads_ready(
        self,
        *,
        series_id: str,
        aligned_time: int,
        factor_out_of_sync_code: str,
        overlay_out_of_sync_code: str,
        factor_out_of_sync_detail: str = "ledger_out_of_sync:factor",
        overlay_out_of_sync_detail: str = "ledger_out_of_sync:overlay",
    ) -> LedgerHeadTimes: ...


@dataclass(frozen=True)
class ReplayPrepareService:
    store: AlignedStorePort
    factor_store: HeadStorePort
    overlay_store: HeadStorePort
    ingest_pipeline: IngestPipelineSyncPort
    debug_hub: DebugHubPort
    ledger_sync_service: _LedgerSyncLike | None = None
    enable_ledger_sync_service: bool = False
    debug_api_enabled: bool = False

    @staticmethod
    def _clamp_window_candles(window_candles: int | None) -> int:
        value = int(window_candles or 2000)
        return min(5000, max(100, value))

    def prepare(self, payload: ReplayPrepareRequestV1) -> ReplayPrepareResponseV1:
        series_id = payload.series_id
        ledger_sync = self.ledger_sync_service
        use_ledger_sync = bool(self.enable_ledger_sync_service and ledger_sync is not None)
        if use_ledger_sync and ledger_sync is not None:
            point = ledger_sync.resolve_aligned_point(
                series_id=series_id,
                to_time=payload.to_time,
                no_data_code="replay_prepare.no_data",
                no_data_detail="no_data",
            )
        else:
            point = require_aligned_point(
                store=self.store,
                series_id=series_id,
                to_time=payload.to_time,
                no_data_code="replay_prepare.no_data",
                no_data_detail="no_data",
            )
        requested_time = int(point.requested_time)
        aligned = int(point.aligned_time)
        window_candles = self._clamp_window_candles(payload.window_candles)

        computed = False
        if use_ledger_sync and ledger_sync is not None:
            refresh_outcome = ledger_sync.refresh_if_needed(
                series_id=series_id,
                up_to_time=int(aligned),
            )
            computed = bool(refresh_outcome.refreshed)
            heads = ledger_sync.require_heads_ready(
                series_id=series_id,
                aligned_time=int(aligned),
                factor_out_of_sync_code="replay_prepare.ledger_out_of_sync.factor",
                overlay_out_of_sync_code="replay_prepare.ledger_out_of_sync.overlay",
                factor_out_of_sync_detail="ledger_out_of_sync:factor",
                overlay_out_of_sync_detail="ledger_out_of_sync:overlay",
            )
        else:
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

            heads = require_ledger_heads_ready(
                factor_store=self.factor_store,
                overlay_store=self.overlay_store,
                series_id=series_id,
                aligned_time=int(aligned),
                factor_out_of_sync_code="replay_prepare.ledger_out_of_sync.factor",
                overlay_out_of_sync_code="replay_prepare.ledger_out_of_sync.overlay",
                factor_out_of_sync_detail="ledger_out_of_sync:factor",
                overlay_out_of_sync_detail="ledger_out_of_sync:overlay",
            )
        factor_head = int(heads.factor_head_time)
        overlay_head = int(heads.overlay_head_time)

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
