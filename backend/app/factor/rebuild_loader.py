from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..debug.hub import DebugHub
from .graph import FactorGraph
from .registry import FactorRegistry
from .runtime_contract import FactorRuntimeContext
from .store import FactorStore
from .pen import PivotMajorPoint


@dataclass(frozen=True)
class RebuildEventBuckets:
    events_by_factor: dict[str, list[dict[str, Any]]]
    rows_count: int
    rows_truncated: bool


@dataclass(frozen=True)
class FactorBootstrapState:
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    last_major_idx: int | None
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    sr_major_pivots: list[dict[str, Any]]
    sr_snapshot: dict[str, Any]


@dataclass
class _BootstrapReplayState:
    head_time: int
    candles: list[Any]
    time_to_idx: dict[int, int]
    rebuild_events: dict[str, list[dict[str, Any]]]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    last_major_idx: int | None
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    sr_major_pivots: list[dict[str, Any]]
    sr_snapshot: dict[str, Any]


class FactorRebuildStateLoader:
    def __init__(
        self,
        *,
        factor_store: FactorStore,
        registry: FactorRegistry,
        graph: FactorGraph,
        runtime: FactorRuntimeContext,
        debug_hub: DebugHub | None = None,
    ) -> None:
        self._factor_store = factor_store
        self._registry = registry
        self._graph = graph
        self._runtime = runtime
        self._debug_hub = debug_hub

    def _bucket_rebuild_event_row(
        self,
        row: Any,
        *,
        events_by_factor: dict[str, list[dict[str, Any]]],
    ) -> None:
        factor_name = str(row.factor_name or "")
        plugin = self._registry.get(factor_name)
        if plugin is None:
            return
        collector = getattr(plugin, "collect_rebuild_event", None)
        if not callable(collector):
            return
        collector(
            kind=str(row.kind),
            payload=dict(row.payload or {}),
            events=events_by_factor.setdefault(factor_name, []),
        )

    def _emit_rebuild_limit_reached(
        self,
        *,
        series_id: str,
        state_start: int,
        head_time: int,
        scan_limit: int,
        rows_count: int,
    ) -> None:
        if self._debug_hub is None:
            return
        self._debug_hub.emit(
            pipe="write",
            event="factor.state_rebuild.limit_reached",
            series_id=series_id,
            message="state rebuild event scan reached limit; switched to paged full scan",
            data={
                "state_start": int(state_start),
                "head_time": int(head_time),
                "scan_limit": int(scan_limit),
                "rows": int(rows_count),
                "mode": "paged_full_scan",
            },
        )

    def collect_rebuild_event_buckets(
        self,
        *,
        series_id: str,
        state_start: int,
        head_time: int,
        scan_limit: int,
    ) -> RebuildEventBuckets:
        rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(state_start),
            end_candle_time=int(head_time),
            limit=int(scan_limit),
        )
        rows_truncated = len(rows) >= int(scan_limit)
        row_iter: Iterable[Any]
        if rows_truncated:
            row_iter = self._factor_store.iter_events_between_times_paged(
                series_id=series_id,
                factor_name=None,
                start_candle_time=int(state_start),
                end_candle_time=int(head_time),
                page_size=int(scan_limit),
            )
        else:
            row_iter = rows

        events_by_factor: dict[str, list[dict[str, Any]]] = {
            str(factor_name): [] for factor_name in self._graph.topo_order
        }
        rows_count = 0

        for row in row_iter:
            rows_count += 1
            self._bucket_rebuild_event_row(row, events_by_factor=events_by_factor)

        if rows_truncated:
            self._emit_rebuild_limit_reached(
                series_id=series_id,
                state_start=int(state_start),
                head_time=int(head_time),
                scan_limit=int(scan_limit),
                rows_count=int(rows_count),
            )

        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            sorter = getattr(plugin, "sort_rebuild_events", None)
            events = events_by_factor.setdefault(str(factor_name), [])
            if callable(sorter):
                sorter(events=events)

        return RebuildEventBuckets(
            events_by_factor=events_by_factor,
            rows_count=int(rows_count),
            rows_truncated=bool(rows_truncated),
        )

    def build_incremental_bootstrap_state(
        self,
        *,
        series_id: str,
        head_time: int,
        lookback_candles: int,
        tf_s: int,
        state_rebuild_event_limit: int,
        candles: list[Any],
        time_to_idx: dict[int, int],
    ) -> FactorBootstrapState:
        state_start = max(0, int(head_time) - int(lookback_candles) * int(tf_s))
        state_scan_limit = max(int(state_rebuild_event_limit), int(lookback_candles) * 8)
        rebuild_events = self.collect_rebuild_event_buckets(
            series_id=series_id,
            state_start=int(state_start),
            head_time=int(head_time),
            scan_limit=int(state_scan_limit),
        )
        state = _BootstrapReplayState(
            head_time=int(head_time),
            candles=candles,
            time_to_idx=time_to_idx,
            rebuild_events=rebuild_events.events_by_factor,
            effective_pivots=[],
            confirmed_pens=[],
            zhongshu_state={},
            last_major_idx=None,
            anchor_current_ref=None,
            anchor_strength=None,
            sr_major_pivots=[],
            sr_snapshot={},
        )
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            bootstrap = getattr(plugin, "bootstrap_from_history", None)
            if not callable(bootstrap):
                continue
            bootstrap(series_id=series_id, state=state, runtime=self._runtime)
        return FactorBootstrapState(
            effective_pivots=state.effective_pivots,
            confirmed_pens=state.confirmed_pens,
            zhongshu_state=state.zhongshu_state,
            last_major_idx=state.last_major_idx,
            anchor_current_ref=state.anchor_current_ref,
            anchor_strength=state.anchor_strength,
            sr_major_pivots=state.sr_major_pivots,
            sr_snapshot=state.sr_snapshot,
        )
