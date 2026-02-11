from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .ledger_alignment import LedgerAlignedPoint, LedgerHeadTimes, require_aligned_point, require_ledger_heads_ready


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
    def steps(self) -> tuple[_PipelineStepLike, ...] | list[_PipelineStepLike]: ...


class _IngestPipelineLike(Protocol):
    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]) -> _RefreshResultLike: ...


@dataclass(frozen=True)
class LedgerHeadSnapshot:
    factor_head_time: int | None
    overlay_head_time: int | None


@dataclass(frozen=True)
class LedgerRefreshOutcome:
    refreshed: bool
    step_names: tuple[str, ...]
    factor_head_time: int | None
    overlay_head_time: int | None


@dataclass(frozen=True)
class LedgerSyncService:
    store: _StoreLike
    factor_store: _HeadStoreLike
    overlay_store: _HeadStoreLike
    ingest_pipeline: _IngestPipelineLike

    @staticmethod
    def _safe_head_time(store: _HeadStoreLike, *, series_id: str) -> int | None:
        try:
            head = store.head_time(series_id)
        except Exception:
            return None
        if head is None:
            return None
        try:
            return int(head)
        except Exception:
            return None

    def resolve_aligned_point(
        self,
        *,
        series_id: str,
        to_time: int | None,
        no_data_code: str,
        no_data_detail: str = "no_data",
    ) -> LedgerAlignedPoint:
        return require_aligned_point(
            store=self.store,
            series_id=series_id,
            to_time=to_time,
            no_data_code=no_data_code,
            no_data_detail=no_data_detail,
        )

    def head_snapshot(self, *, series_id: str) -> LedgerHeadSnapshot:
        return LedgerHeadSnapshot(
            factor_head_time=self._safe_head_time(self.factor_store, series_id=series_id),
            overlay_head_time=self._safe_head_time(self.overlay_store, series_id=series_id),
        )

    def refresh(self, *, series_id: str, up_to_time: int) -> LedgerRefreshOutcome:
        refresh_result = self.ingest_pipeline.refresh_series_sync(up_to_times={str(series_id): int(up_to_time)})
        steps = tuple(getattr(refresh_result, "steps", tuple()) or tuple())
        step_names = tuple(str(step.name) for step in steps)
        snapshot = self.head_snapshot(series_id=series_id)
        return LedgerRefreshOutcome(
            refreshed=bool(step_names),
            step_names=step_names,
            factor_head_time=snapshot.factor_head_time,
            overlay_head_time=snapshot.overlay_head_time,
        )

    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> LedgerRefreshOutcome:
        target_time = int(up_to_time)
        before = self.head_snapshot(series_id=series_id)
        factor_ready = before.factor_head_time is not None and int(before.factor_head_time) >= target_time
        overlay_ready = before.overlay_head_time is not None and int(before.overlay_head_time) >= target_time
        if factor_ready and overlay_ready:
            return LedgerRefreshOutcome(
                refreshed=False,
                step_names=tuple(),
                factor_head_time=before.factor_head_time,
                overlay_head_time=before.overlay_head_time,
            )
        return self.refresh(series_id=series_id, up_to_time=int(target_time))

    def require_heads_ready(
        self,
        *,
        series_id: str,
        aligned_time: int,
        factor_out_of_sync_code: str,
        overlay_out_of_sync_code: str,
        factor_out_of_sync_detail: str = "ledger_out_of_sync:factor",
        overlay_out_of_sync_detail: str = "ledger_out_of_sync:overlay",
    ) -> LedgerHeadTimes:
        return require_ledger_heads_ready(
            factor_store=self.factor_store,
            overlay_store=self.overlay_store,
            series_id=series_id,
            aligned_time=int(aligned_time),
            factor_out_of_sync_code=factor_out_of_sync_code,
            overlay_out_of_sync_code=overlay_out_of_sync_code,
            factor_out_of_sync_detail=factor_out_of_sync_detail,
            overlay_out_of_sync_detail=overlay_out_of_sync_detail,
        )
