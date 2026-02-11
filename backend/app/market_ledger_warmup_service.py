from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .shared_ports import DebugHubPort, HeadStorePort, IngestPipelineSyncPort


class _RuntimeFlagsLike(Protocol):
    @property
    def enable_read_ledger_warmup(self) -> bool: ...

    @property
    def enable_debug_api(self) -> bool: ...

    @property
    def enable_ledger_sync_service(self) -> bool: ...


class _LedgerRefreshOutcomeLike(Protocol):
    @property
    def refreshed(self) -> bool: ...

    @property
    def step_names(self) -> tuple[str, ...]: ...

    @property
    def factor_head_time(self) -> int | None: ...

    @property
    def overlay_head_time(self) -> int | None: ...


class _LedgerHeadSnapshotLike(Protocol):
    @property
    def factor_head_time(self) -> int | None: ...

    @property
    def overlay_head_time(self) -> int | None: ...


class _LedgerSyncLike(Protocol):
    def head_snapshot(self, *, series_id: str) -> _LedgerHeadSnapshotLike: ...

    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> _LedgerRefreshOutcomeLike: ...


@dataclass(frozen=True)
class MarketLedgerWarmupService:
    factor_store: HeadStorePort | None
    overlay_store: HeadStorePort | None
    ingest_pipeline: IngestPipelineSyncPort | None
    runtime_flags: _RuntimeFlagsLike
    debug_hub: DebugHubPort
    ledger_sync_service: _LedgerSyncLike | None = None

    def _use_ledger_sync_service(self) -> bool:
        return bool(self.runtime_flags.enable_ledger_sync_service and self.ledger_sync_service is not None)

    def _enabled(self) -> bool:
        if not bool(self.runtime_flags.enable_read_ledger_warmup):
            return False
        if self._use_ledger_sync_service():
            return True
        return bool(
            self.factor_store is not None
            and self.overlay_store is not None
            and self.ingest_pipeline is not None
        )

    @staticmethod
    def _safe_head_time(store: HeadStorePort | None, *, series_id: str) -> int | None:
        if store is None:
            return None
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

    def ensure_ledgers_warm(self, *, series_id: str, store_head_time: int | None) -> None:
        if not self._enabled():
            return
        if store_head_time is None or int(store_head_time) <= 0:
            return
        target_time = int(store_head_time)
        step_names: list[str] = []
        err: Exception | None = None
        ledger_sync = self.ledger_sync_service
        use_ledger_sync = bool(self.runtime_flags.enable_ledger_sync_service and ledger_sync is not None)

        if use_ledger_sync and ledger_sync is not None:
            snapshot = ledger_sync.head_snapshot(series_id=series_id)
            factor_head_before = None if snapshot.factor_head_time is None else int(snapshot.factor_head_time)
            overlay_head_before = None if snapshot.overlay_head_time is None else int(snapshot.overlay_head_time)
            factor_head_after = factor_head_before
            overlay_head_after = overlay_head_before
            try:
                refresh = ledger_sync.refresh_if_needed(
                    series_id=series_id,
                    up_to_time=int(target_time),
                )
                step_names = list(refresh.step_names)
                factor_head_after = None if refresh.factor_head_time is None else int(refresh.factor_head_time)
                overlay_head_after = None if refresh.overlay_head_time is None else int(refresh.overlay_head_time)
            except Exception as exc:
                err = exc
        else:
            factor_head_before = self._safe_head_time(self.factor_store, series_id=series_id)
            overlay_head_before = self._safe_head_time(self.overlay_store, series_id=series_id)
            factor_ready = factor_head_before is not None and int(factor_head_before) >= target_time
            overlay_ready = overlay_head_before is not None and int(overlay_head_before) >= target_time
            if factor_ready and overlay_ready:
                return

            pipeline = self.ingest_pipeline
            if pipeline is None:
                return
            try:
                refresh_result = pipeline.refresh_series_sync(up_to_times={series_id: int(target_time)})
                step_names = [str(step.name) for step in tuple(refresh_result.steps)]
            except Exception as exc:
                err = exc

            factor_head_after = self._safe_head_time(self.factor_store, series_id=series_id)
            overlay_head_after = self._safe_head_time(self.overlay_store, series_id=series_id)
        if bool(self.runtime_flags.enable_debug_api):
            payload: dict[str, object] = {
                "target_time": int(target_time),
                "factor_head_before": None if factor_head_before is None else int(factor_head_before),
                "overlay_head_before": None if overlay_head_before is None else int(overlay_head_before),
                "factor_head_after": None if factor_head_after is None else int(factor_head_after),
                "overlay_head_after": None if overlay_head_after is None else int(overlay_head_after),
                "steps": step_names,
            }
            if err is not None:
                payload["error"] = str(err)
            self.debug_hub.emit(
                pipe="read",
                event="read.http.market_candles_ledger_warmup",
                level="warn" if err is not None else "info",
                series_id=series_id,
                message="ensure factor/overlay ledgers are warm",
                data=payload,
            )
