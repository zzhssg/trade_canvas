from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Literal
from typing import TYPE_CHECKING, Protocol

from .backfill_tracker import BackfillProgressSnapshot
from ..core.series_id import parse_series_id
from ..core.timeframe import timeframe_to_seconds

if TYPE_CHECKING:
    from ..market_data import FreshnessSnapshot

KlineHealthStatus = Literal["green", "yellow", "red", "gray"]


@dataclass(frozen=True)
class BackfillHealthView:
    state: str
    progress_pct: float | None
    started_at: int | None
    updated_at: int | None
    reason: str | None
    note: str | None
    error: str | None
    start_missing_seconds: int
    start_missing_candles: int
    current_missing_seconds: int
    current_missing_candles: int
    recent: bool


@dataclass(frozen=True)
class MarketHealthSnapshot:
    series_id: str
    timeframe_seconds: int
    now_time: int
    expected_latest_closed_time: int
    head_time: int | None
    lag_seconds: int | None
    missing_seconds: int | None
    missing_candles: int | None
    status: KlineHealthStatus
    status_reason: str
    backfill: BackfillHealthView


class _MarketDataLike(Protocol):
    def freshness(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot: ...


class _BackfillProgressLike(Protocol):
    def snapshot(self, *, series_id: str) -> BackfillProgressSnapshot: ...


def _expected_latest_closed_time(*, now_time: int, timeframe_seconds: int) -> int:
    tf = max(1, int(timeframe_seconds))
    aligned = (int(now_time) // tf) * tf
    if aligned <= 0:
        return 0
    if aligned >= tf:
        return int(aligned - tf)
    return 0


def _missing_to_target(*, head_time: int | None, target_time: int, timeframe_seconds: int) -> tuple[int | None, int | None]:
    if head_time is None:
        return None, None
    tf = max(1, int(timeframe_seconds))
    missing_seconds = max(0, int(target_time) - int(head_time))
    missing_candles = max(0, int(math.ceil(float(missing_seconds) / float(tf)))) if missing_seconds > 0 else 0
    return int(missing_seconds), int(missing_candles)


def compute_missing_to_time(*, head_time: int | None, target_time: int, timeframe_seconds: int) -> tuple[int, int]:
    target = max(0, int(target_time))
    tf = max(1, int(timeframe_seconds))
    if head_time is None:
        if target <= 0:
            return 0, 0
        return int(target), max(1, int(math.ceil(float(target) / float(tf))))
    missing_seconds = max(0, int(target) - int(head_time))
    missing_candles = max(0, int(math.ceil(float(missing_seconds) / float(tf)))) if missing_seconds > 0 else 0
    return int(missing_seconds), int(missing_candles)


def _build_backfill_view(*, now_time: int, backfill: BackfillProgressSnapshot, recent_seconds: int) -> BackfillHealthView:
    updated_at = backfill.updated_at
    recent = updated_at is not None and (int(now_time) - int(updated_at)) <= max(0, int(recent_seconds))
    return BackfillHealthView(
        state=backfill.state,
        progress_pct=backfill.progress_pct,
        started_at=backfill.started_at,
        updated_at=backfill.updated_at,
        reason=backfill.reason,
        note=backfill.note,
        error=backfill.error,
        start_missing_seconds=backfill.start_missing_seconds,
        start_missing_candles=backfill.start_missing_candles,
        current_missing_seconds=backfill.current_missing_seconds,
        current_missing_candles=backfill.current_missing_candles,
        recent=bool(recent),
    )


def build_market_health_snapshot(
    *,
    market_data: _MarketDataLike,
    backfill_progress: _BackfillProgressLike,
    series_id: str,
    now_time: int | None = None,
    backfill_recent_seconds: int = 120,
) -> MarketHealthSnapshot:
    now = int(now_time) if now_time is not None else int(time.time())
    series = parse_series_id(series_id)
    tf_s = int(timeframe_to_seconds(series.timeframe))
    expected_latest_closed_time = _expected_latest_closed_time(now_time=now, timeframe_seconds=tf_s)

    freshness = market_data.freshness(series_id=series_id, now_time=now)
    head_time = freshness.head_time
    lag_seconds = freshness.lag_seconds
    missing_seconds, missing_candles = _missing_to_target(
        head_time=head_time,
        target_time=expected_latest_closed_time,
        timeframe_seconds=tf_s,
    )

    backfill_snapshot = backfill_progress.snapshot(series_id=series_id)
    backfill_view = _build_backfill_view(
        now_time=now,
        backfill=backfill_snapshot,
        recent_seconds=backfill_recent_seconds,
    )

    status: KlineHealthStatus
    status_reason: str
    if head_time is None:
        status = "red"
        status_reason = "missing_head"
    elif int(head_time) > int(expected_latest_closed_time):
        status = "yellow"
        status_reason = "head_ahead_of_closed_window"
    elif int(missing_seconds or 0) <= 0:
        status = "green"
        status_reason = "up_to_date"
    elif backfill_view.state == "running":
        status = "yellow"
        status_reason = "backfill_running"
    elif backfill_view.state == "succeeded" and backfill_view.recent:
        status = "yellow"
        status_reason = "backfill_recent"
    else:
        status = "red"
        status_reason = "lagging_no_recent_backfill"

    return MarketHealthSnapshot(
        series_id=series_id,
        timeframe_seconds=tf_s,
        now_time=now,
        expected_latest_closed_time=expected_latest_closed_time,
        head_time=head_time,
        lag_seconds=lag_seconds,
        missing_seconds=missing_seconds,
        missing_candles=missing_candles,
        status=status,
        status_reason=status_reason,
        backfill=backfill_view,
    )
