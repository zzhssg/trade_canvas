from __future__ import annotations

from typing import Protocol


class StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class AlignedStoreLike(StoreLike, Protocol):
    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class BackfillLike(Protocol):
    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int: ...


class LedgerRefreshOutcomeLike(Protocol):
    @property
    def refreshed(self) -> bool: ...


class LedgerSyncLike(Protocol):
    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> LedgerRefreshOutcomeLike: ...


class DebugHubLike(Protocol):
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


class RuntimeReadCtxLike(Protocol):
    @property
    def backfill(self) -> BackfillLike: ...

    @property
    def whitelist(self) -> object: ...


class RuntimeLike(Protocol):
    @property
    def store(self) -> AlignedStoreLike: ...

    @property
    def read_ctx(self) -> RuntimeReadCtxLike: ...

    @property
    def ledger_sync_service(self) -> LedgerSyncLike: ...

    @property
    def debug_hub(self) -> DebugHubLike: ...


def runtime_backfill(runtime: RuntimeLike) -> BackfillLike:
    return runtime.read_ctx.backfill


def runtime_ledger_sync(runtime: RuntimeLike) -> LedgerSyncLike:
    return runtime.ledger_sync_service
