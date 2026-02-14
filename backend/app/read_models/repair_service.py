from __future__ import annotations

from dataclasses import dataclass

from ..core.ports import DebugHubPort
from ..core.schemas import RepairOverlayRequestV1, RepairOverlayResponseV1
from ..core.service_errors import ServiceError
from ..ledger.ports import LedgerSyncRepairPort
from .ports import OverlayOrchestratorReadPort


@dataclass(frozen=True)
class ReadRepairService:
    overlay_orchestrator: OverlayOrchestratorReadPort
    debug_hub: DebugHubPort
    ledger_sync_service: LedgerSyncRepairPort
    debug_api_enabled: bool = False

    def _emit_debug(
        self,
        *,
        series_id: str,
        requested_time: int,
        aligned_time: int,
        step_names: list[str],
        factor_head: int | None,
        overlay_head: int | None,
    ) -> None:
        if not bool(self.debug_api_enabled):
            return
        self.debug_hub.emit(
            pipe="read",
            event="read.http.overlay_repair",
            series_id=series_id,
            message="repair overlay ledger",
            data={
                "requested_time": int(requested_time),
                "aligned_time": int(aligned_time),
                "steps": list(step_names),
                "factor_head_time": None if factor_head is None else int(factor_head),
                "overlay_head_time": None if overlay_head is None else int(overlay_head),
            },
        )

    def repair_overlay(self, payload: RepairOverlayRequestV1) -> RepairOverlayResponseV1:
        series_id = str(payload.series_id)
        ledger_sync = self.ledger_sync_service
        point = ledger_sync.resolve_aligned_point(
            series_id=series_id,
            to_time=payload.to_time,
            no_data_code="read_repair.no_data",
            no_data_detail="no_data",
        )
        requested_time = int(point.requested_time)
        aligned_time = int(point.aligned_time)
        step_names: list[str] = []
        try:
            refresh_outcome = ledger_sync.refresh(
                series_id=series_id,
                up_to_time=int(aligned_time),
            )
            step_names.extend(str(name) for name in tuple(refresh_outcome.step_names))
            self.overlay_orchestrator.reset_series(series_id=series_id)
            step_names.append("overlay.reset_series")
            self.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(aligned_time))
            step_names.append("overlay.ingest_closed")
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(
                status_code=500,
                detail=f"overlay_repair_failed:{exc}",
                code="read_repair.overlay_repair_failed",
            ) from exc

        heads = ledger_sync.require_heads_ready(
            series_id=series_id,
            aligned_time=int(aligned_time),
            factor_out_of_sync_code="read_repair.ledger_out_of_sync.factor",
            overlay_out_of_sync_code="read_repair.ledger_out_of_sync.overlay",
            factor_out_of_sync_detail="ledger_out_of_sync:factor",
            overlay_out_of_sync_detail="ledger_out_of_sync:overlay",
        )
        factor_head = int(heads.factor_head_time)
        overlay_head = int(heads.overlay_head_time)

        self._emit_debug(
            series_id=series_id,
            requested_time=int(requested_time),
            aligned_time=int(aligned_time),
            step_names=step_names,
            factor_head=factor_head,
            overlay_head=overlay_head,
        )
        return RepairOverlayResponseV1(
            ok=True,
            series_id=series_id,
            requested_time=int(requested_time),
            aligned_time=int(aligned_time),
            factor_head_time=int(factor_head),
            overlay_head_time=int(overlay_head),
            refreshed=bool(step_names),
            steps=step_names,
        )
