from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .graph import FactorGraph
from .registry import FactorRegistry
from .runtime_config import FactorSettings
from .runtime_contract import FactorRuntimeContext
from .store import FactorEventWrite
from .pen import PivotMajorPoint
from .tick_state_slices import (
    FactorTickAnchorState,
    FactorTickPenState,
    FactorTickPivotState,
    FactorTickZhongshuState,
)


@dataclass
class FactorTickState:
    visible_time: int
    tf_s: int
    settings: FactorSettings
    candles: list[Any]
    time_to_idx: dict[int, int]
    events: list[FactorEventWrite]
    pivot: FactorTickPivotState
    pen: FactorTickPenState
    zhongshu: FactorTickZhongshuState
    anchor: FactorTickAnchorState

    @property
    def effective_pivots(self) -> list[PivotMajorPoint]:
        return self.pivot.effective_pivots

    @effective_pivots.setter
    def effective_pivots(self, value: list[PivotMajorPoint]) -> None:
        self.pivot.effective_pivots = value

    @property
    def last_major_idx(self) -> int | None:
        return self.pivot.last_major_idx

    @last_major_idx.setter
    def last_major_idx(self, value: int | None) -> None:
        self.pivot.last_major_idx = value

    @property
    def major_candidates(self) -> list[PivotMajorPoint]:
        return self.pivot.major_candidates

    @major_candidates.setter
    def major_candidates(self, value: list[PivotMajorPoint]) -> None:
        self.pivot.major_candidates = value

    @property
    def confirmed_pens(self) -> list[dict[str, Any]]:
        return self.pen.confirmed_pens

    @confirmed_pens.setter
    def confirmed_pens(self, value: list[dict[str, Any]]) -> None:
        self.pen.confirmed_pens = value

    @property
    def new_confirmed_pen_payloads(self) -> list[dict[str, Any]]:
        return self.pen.new_confirmed_pen_payloads

    @new_confirmed_pen_payloads.setter
    def new_confirmed_pen_payloads(self, value: list[dict[str, Any]]) -> None:
        self.pen.new_confirmed_pen_payloads = value

    @property
    def zhongshu_state(self) -> dict[str, Any]:
        return self.zhongshu.payload

    @zhongshu_state.setter
    def zhongshu_state(self, value: dict[str, Any]) -> None:
        self.zhongshu.payload = value

    @property
    def formed_entries(self) -> list[dict[str, Any]]:
        return self.zhongshu.formed_entries

    @formed_entries.setter
    def formed_entries(self, value: list[dict[str, Any]]) -> None:
        self.zhongshu.formed_entries = value

    @property
    def anchor_current_ref(self) -> dict[str, Any] | None:
        return self.anchor.current_ref

    @anchor_current_ref.setter
    def anchor_current_ref(self, value: dict[str, Any] | None) -> None:
        self.anchor.current_ref = value

    @property
    def anchor_strength(self) -> float | None:
        return self.anchor.strength

    @anchor_strength.setter
    def anchor_strength(self, value: float | None) -> None:
        self.anchor.strength = value

    @property
    def best_strong_pen_ref(self) -> dict[str, int | str] | None:
        return self.anchor.best_strong_pen_ref

    @best_strong_pen_ref.setter
    def best_strong_pen_ref(self, value: dict[str, int | str] | None) -> None:
        self.anchor.best_strong_pen_ref = value

    @property
    def best_strong_pen_strength(self) -> float | None:
        return self.anchor.best_strong_pen_strength

    @best_strong_pen_strength.setter
    def best_strong_pen_strength(self, value: float | None) -> None:
        self.anchor.best_strong_pen_strength = value

    @property
    def baseline_anchor_strength(self) -> float | None:
        return self.anchor.baseline_strength

    @baseline_anchor_strength.setter
    def baseline_anchor_strength(self, value: float | None) -> None:
        self.anchor.baseline_strength = value


@dataclass(frozen=True)
class FactorTickExecutionResult:
    events: list[FactorEventWrite]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None


@dataclass(frozen=True)
class FactorTickRunRequest:
    series_id: str
    process_times: list[int]
    tf_s: int
    settings: FactorSettings
    candles: list[Any]
    time_to_idx: dict[int, int]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None
    events: list[FactorEventWrite] | None = None


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
        request: FactorTickRunRequest,
    ) -> FactorTickExecutionResult:
        out_events: list[FactorEventWrite] = request.events if request.events is not None else []
        cur_anchor_current_ref = request.anchor_current_ref
        cur_anchor_strength = request.anchor_strength
        cur_last_major_idx = request.last_major_idx

        for visible_time in request.process_times:
            tick_state = FactorTickState(
                visible_time=int(visible_time),
                tf_s=int(request.tf_s),
                settings=request.settings,
                candles=request.candles,
                time_to_idx=request.time_to_idx,
                events=out_events,
                pivot=FactorTickPivotState(
                    effective_pivots=request.effective_pivots,
                    last_major_idx=cur_last_major_idx,
                    major_candidates=[],
                ),
                pen=FactorTickPenState(
                    confirmed_pens=request.confirmed_pens,
                    new_confirmed_pen_payloads=[],
                ),
                zhongshu=FactorTickZhongshuState(
                    payload=request.zhongshu_state,
                    formed_entries=[],
                ),
                anchor=FactorTickAnchorState(
                    current_ref=cur_anchor_current_ref,
                    strength=cur_anchor_strength,
                    best_strong_pen_ref=None,
                    best_strong_pen_strength=None,
                    baseline_strength=float(cur_anchor_strength) if cur_anchor_strength is not None else None,
                ),
            )
            self.run_tick_steps(series_id=request.series_id, state=tick_state)
            cur_anchor_current_ref = tick_state.anchor_current_ref
            cur_anchor_strength = tick_state.anchor_strength
            cur_last_major_idx = tick_state.last_major_idx

        return FactorTickExecutionResult(
            events=out_events,
            effective_pivots=request.effective_pivots,
            confirmed_pens=request.confirmed_pens,
            zhongshu_state=request.zhongshu_state,
            anchor_current_ref=cur_anchor_current_ref,
            anchor_strength=cur_anchor_strength,
            last_major_idx=cur_last_major_idx,
        )
