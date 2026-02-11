from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from ..schemas import RepairOverlayRequestV1, RepairOverlayResponseV1
from ..service_errors import ServiceError


class _StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class _HeadStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class _PipelineStepLike(Protocol):
    @property
    def name(self) -> str: ...


class _RefreshResultLike(Protocol):
    @property
    def steps(self) -> tuple[_PipelineStepLike, ...]: ...


class _IngestPipelineLike(Protocol):
    def refresh_series_sync(
        self,
        *,
        up_to_times: Mapping[str, int],
    ) -> _RefreshResultLike: ...


class _OverlayOrchestratorLike(Protocol):
    def reset_series(self, *, series_id: str) -> None: ...

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...


class _DebugHubLike(Protocol):
    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class ReadRepairService:
    store: _StoreLike
    factor_store: _HeadStoreLike
    overlay_store: _HeadStoreLike
    ingest_pipeline: _IngestPipelineLike
    overlay_orchestrator: _OverlayOrchestratorLike
    debug_hub: _DebugHubLike
    debug_api_enabled: bool = False

    def _require_aligned_time(self, *, series_id: str, to_time: int | None) -> tuple[int, int]:
        store_head = self.store.head_time(series_id)
        if store_head is None:
            raise ServiceError(status_code=404, detail="no_data", code="read_repair.no_data")

        requested_time = int(to_time) if to_time is not None else int(store_head)
        aligned = self.store.floor_time(series_id, at_time=int(requested_time))
        if aligned is None:
            raise ServiceError(status_code=404, detail="no_data", code="read_repair.no_data")
        return int(requested_time), int(aligned)

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
        requested_time, aligned_time = self._require_aligned_time(series_id=series_id, to_time=payload.to_time)
        step_names: list[str] = []
        try:
            refresh_result = self.ingest_pipeline.refresh_series_sync(up_to_times={series_id: int(aligned_time)})
            step_names.extend(str(step.name) for step in tuple(refresh_result.steps))
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

        factor_head = self.factor_store.head_time(series_id)
        overlay_head = self.overlay_store.head_time(series_id)
        if factor_head is None or int(factor_head) < int(aligned_time):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:factor",
                code="read_repair.ledger_out_of_sync.factor",
            )
        if overlay_head is None or int(overlay_head) < int(aligned_time):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:overlay",
                code="read_repair.ledger_out_of_sync.overlay",
            )

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
