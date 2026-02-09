from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..schemas import CandleClosed

FreshnessState = Literal["missing", "fresh", "stale", "degraded"]


@dataclass(frozen=True)
class FreshnessSnapshot:
    series_id: str
    head_time: int | None
    now_time: int
    lag_seconds: int | None
    state: FreshnessState


@dataclass(frozen=True)
class BackfillGapRequest:
    series_id: str
    expected_next_time: int
    actual_time: int


@dataclass(frozen=True)
class BackfillGapResult:
    series_id: str
    expected_next_time: int
    actual_time: int
    filled_count: int


@dataclass(frozen=True)
class CatchupReadRequest:
    series_id: str
    since: int | None
    limit: int


@dataclass(frozen=True)
class CatchupReadResult:
    series_id: str
    effective_since: int | None
    candles: list[CandleClosed]
    gap_payload: dict | None


@dataclass(frozen=True)
class WsCatchupRequest:
    series_id: str
    since: int | None
    last_sent: int | None
    limit: int
    candles: list[CandleClosed] | None = None


@dataclass(frozen=True)
class WsEmitRequest:
    series_id: str
    supports_batch: bool
    catchup: list[CandleClosed]
    gap_payload: dict | None


@dataclass(frozen=True)
class WsEmitResult:
    payloads: list[dict]
    last_sent_time: int | None


class CandleReadService(Protocol):
    def read_tail(self, *, series_id: str, limit: int) -> list[CandleClosed]: ...

    def read_incremental(self, *, series_id: str, since: int, limit: int) -> list[CandleClosed]: ...

    def read_between(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[CandleClosed]: ...


class BackfillService(Protocol):
    def backfill_gap(self, req: BackfillGapRequest) -> BackfillGapResult: ...

    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int: ...


class FreshnessService(Protocol):
    def snapshot(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot: ...


class WsDeliveryService(Protocol):
    async def heal_catchup_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]: ...


class MarketDataOrchestrator(Protocol):
    def freshness(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot: ...

    def read_candles(self, req: CatchupReadRequest) -> CatchupReadResult: ...

    async def build_ws_catchup(self, req: WsCatchupRequest) -> CatchupReadResult: ...

    def build_ws_emit(self, req: WsEmitRequest) -> WsEmitResult: ...

    async def heal_ws_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]: ...
