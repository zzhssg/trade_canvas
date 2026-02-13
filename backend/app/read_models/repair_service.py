from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..ledger.alignment import LedgerAlignedPoint, LedgerHeadTimes
from ..schemas import RepairOverlayRequestV1, RepairOverlayResponseV1
from ..shared_ports import DebugHubPort
from ..service_errors import ServiceError


class _OverlayOrchestratorLike(Protocol):
    def reset_series(self, *, series_id: str) -> None: ...

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...


class _LedgerSyncLike(Protocol):
    def resolve_aligned_point(
        self,
        *,
        series_id: str,
        to_time: int | None,
        no_data_code: str,
        no_data_detail: str = "no_data",
    ) -> LedgerAlignedPoint: ...

    def refresh(self, *, series_id: str, up_to_time: int): ...

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
class ReadRepairService:
    overlay_orchestrator: _OverlayOrchestratorLike
    debug_hub: DebugHubPort
    ledger_sync_service: _LedgerSyncLike
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
