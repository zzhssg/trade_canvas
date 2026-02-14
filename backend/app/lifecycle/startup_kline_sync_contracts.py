from __future__ import annotations

from typing import Protocol

from ..core.ports import AlignedStorePort, BackfillPort, DebugHubPort
from ..ledger.ports import LedgerSyncPreparePort


class RuntimeReadCtxLike(Protocol):
    @property
    def backfill(self) -> BackfillPort: ...

    @property
    def whitelist(self) -> object: ...


class RuntimeLike(Protocol):
    @property
    def store(self) -> AlignedStorePort: ...

    @property
    def read_ctx(self) -> RuntimeReadCtxLike: ...

    @property
    def ledger_sync_service(self) -> LedgerSyncPreparePort: ...

    @property
    def debug_hub(self) -> DebugHubPort: ...


def runtime_backfill(runtime: RuntimeLike) -> BackfillPort:
    return runtime.read_ctx.backfill


def runtime_ledger_sync(runtime: RuntimeLike) -> LedgerSyncPreparePort:
    return runtime.ledger_sync_service
