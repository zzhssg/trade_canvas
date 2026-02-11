from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .factor_graph import FactorGraph
from .factor_registry import FactorRegistry
from .factor_runtime_config import FactorSettings
from .factor_runtime_contract import FactorRuntimeContext
from .factor_store import FactorEventWrite
from .pen import PivotMajorPoint


@dataclass
class FactorTickState:
    visible_time: int
    tf_s: int
    settings: FactorSettings
    candles: list[Any]
    time_to_idx: dict[int, int]
    events: list[FactorEventWrite]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None
    major_candidates: list[PivotMajorPoint]
    new_confirmed_pen_payloads: list[dict[str, Any]]
    formed_entries: list[dict[str, Any]]
    best_strong_pen_ref: dict[str, int | str] | None
    best_strong_pen_strength: float | None
    baseline_anchor_strength: float | None


@dataclass(frozen=True)
class FactorTickExecutionResult:
    events: list[FactorEventWrite]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None


class FactorTickExecutor:
    def __init__(
        self,
        *,
        graph: FactorGraph,
        registry: FactorRegistry,
        runtime: FactorRuntimeContext,
    ) -> None:
        self._graph = graph
        self._registry = registry
        self._runtime = runtime

    def run_tick_steps(self, *, series_id: str, state: FactorTickState) -> None:
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            run_tick = getattr(plugin, "run_tick", None)
            if not callable(run_tick):
                raise RuntimeError(f"factor_missing_run_tick:{factor_name}")
            run_tick(series_id=series_id, state=state, runtime=self._runtime)

    def run_incremental(
        self,
        *,
        series_id: str,
        process_times: list[int],
        tf_s: int,
        settings: FactorSettings,
        candles: list[Any],
        time_to_idx: dict[int, int],
        effective_pivots: list[PivotMajorPoint],
        confirmed_pens: list[dict[str, Any]],
        zhongshu_state: dict[str, Any],
        anchor_current_ref: dict[str, Any] | None,
        anchor_strength: float | None,
        last_major_idx: int | None,
        events: list[FactorEventWrite] | None = None,
    ) -> FactorTickExecutionResult:
        out_events: list[FactorEventWrite] = events if events is not None else []
        cur_anchor_current_ref = anchor_current_ref
        cur_anchor_strength = anchor_strength
        cur_last_major_idx = last_major_idx

        for visible_time in process_times:
            tick_state = FactorTickState(
                visible_time=int(visible_time),
                tf_s=int(tf_s),
                settings=settings,
                candles=candles,
                time_to_idx=time_to_idx,
                events=out_events,
                effective_pivots=effective_pivots,
                confirmed_pens=confirmed_pens,
                zhongshu_state=zhongshu_state,
                anchor_current_ref=cur_anchor_current_ref,
                anchor_strength=cur_anchor_strength,
                last_major_idx=cur_last_major_idx,
                major_candidates=[],
                new_confirmed_pen_payloads=[],
                formed_entries=[],
                best_strong_pen_ref=None,
                best_strong_pen_strength=None,
                baseline_anchor_strength=float(cur_anchor_strength) if cur_anchor_strength is not None else None,
            )
            self.run_tick_steps(series_id=series_id, state=tick_state)
            cur_anchor_current_ref = tick_state.anchor_current_ref
            cur_anchor_strength = tick_state.anchor_strength
            cur_last_major_idx = tick_state.last_major_idx

        return FactorTickExecutionResult(
            events=out_events,
            effective_pivots=effective_pivots,
            confirmed_pens=confirmed_pens,
            zhongshu_state=zhongshu_state,
            anchor_current_ref=cur_anchor_current_ref,
            anchor_strength=cur_anchor_strength,
            last_major_idx=cur_last_major_idx,
        )
