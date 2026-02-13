from __future__ import annotations

from typing import Any

from .rebuild_loader import FactorBootstrapState, FactorRebuildStateLoader, RebuildEventBuckets
from .tick_executor import (
    FactorTickExecutionResult,
    FactorTickExecutor,
    FactorTickRunRequest,
    FactorTickState,
)


def run_tick_steps(*, tick_executor: FactorTickExecutor, series_id: str, state: FactorTickState) -> None:
    tick_executor.run_tick_steps(series_id=series_id, state=state)


def run_ticks(
    *,
    tick_executor: FactorTickExecutor,
    request: FactorTickRunRequest,
) -> FactorTickExecutionResult:
    return tick_executor.run_incremental(
        request=request,
    )


def collect_rebuild_event_buckets(
    *,
    loader: FactorRebuildStateLoader,
    series_id: str,
    state_start: int,
    head_time: int,
    scan_limit: int,
) -> RebuildEventBuckets:
    return loader.collect_rebuild_event_buckets(
        series_id=series_id,
        state_start=int(state_start),
        head_time=int(head_time),
        scan_limit=int(scan_limit),
    )


def build_incremental_bootstrap_state(
    *,
    loader: FactorRebuildStateLoader,
    series_id: str,
    head_time: int,
    lookback_candles: int,
    tf_s: int,
    state_rebuild_event_limit: int,
    candles: list[Any],
    time_to_idx: dict[int, int],
) -> FactorBootstrapState:
    return loader.build_incremental_bootstrap_state(
        series_id=series_id,
        head_time=int(head_time),
        lookback_candles=int(lookback_candles),
        tf_s=int(tf_s),
        state_rebuild_event_limit=int(state_rebuild_event_limit),
        candles=candles,
        time_to_idx=time_to_idx,
    )
