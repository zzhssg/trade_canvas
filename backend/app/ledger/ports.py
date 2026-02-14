from __future__ import annotations

from typing import Protocol

from .alignment import LedgerAlignedPoint, LedgerHeadTimes


class LedgerRefreshOutcomePort(Protocol):
    @property
    def refreshed(self) -> bool: ...

    @property
    def step_names(self) -> tuple[str, ...] | list[str]: ...

    @property
    def factor_head_time(self) -> int | None: ...

    @property
    def overlay_head_time(self) -> int | None: ...


class LedgerSyncBasePort(Protocol):
    def resolve_aligned_point(
        self,
        *,
        series_id: str,
        to_time: int | None,
        no_data_code: str,
        no_data_detail: str = "no_data",
    ) -> LedgerAlignedPoint: ...

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


class LedgerSyncPreparePort(LedgerSyncBasePort, Protocol):
    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> LedgerRefreshOutcomePort: ...


class LedgerSyncRepairPort(LedgerSyncBasePort, Protocol):
    def refresh(self, *, series_id: str, up_to_time: int) -> LedgerRefreshOutcomePort: ...


LedgerSyncPort = LedgerSyncPreparePort | LedgerSyncRepairPort
