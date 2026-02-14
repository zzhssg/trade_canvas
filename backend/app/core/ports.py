from __future__ import annotations

from typing import Mapping, Protocol

from .schemas import CandleClosed


class AlignedStorePort(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class HeadStorePort(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class PipelineStepPort(Protocol):
    @property
    def name(self) -> str: ...


class RefreshResultPort(Protocol):
    @property
    def steps(self) -> tuple[PipelineStepPort, ...] | list[PipelineStepPort]: ...


class IngestPipelineSyncPort(Protocol):
    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]) -> RefreshResultPort: ...


class FactorIngestResultPort(Protocol):
    @property
    def rebuilt(self) -> bool: ...


class FactorOrchestratorPort(Protocol):
    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> FactorIngestResultPort: ...


class DebugApiFlagsPort(Protocol):
    @property
    def enable_debug_api(self) -> bool: ...


class MarketAutoTailBackfillFlagsPort(Protocol):
    @property
    def enable_market_auto_tail_backfill(self) -> bool: ...

    @property
    def market_auto_tail_backfill_max_candles(self) -> int | None: ...


class MarketQueryFlagsPort(MarketAutoTailBackfillFlagsPort, DebugApiFlagsPort, Protocol):
    pass


class ReadLedgerWarmupFlagsPort(DebugApiFlagsPort, Protocol):
    @property
    def enable_read_ledger_warmup(self) -> bool: ...


class BackfillPort(Protocol):
    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int: ...


class OverlayOrchestratorPort(Protocol):
    def reset_series(self, *, series_id: str) -> None: ...

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...


class DebugHubPort(Protocol):
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


class CandleHubPort(Protocol):
    async def publish_closed(self, *, series_id: str, candle: CandleClosed) -> None: ...

    async def publish_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> None: ...

    async def publish_system(self, *, series_id: str, event: str, message: str, data: dict) -> None: ...
