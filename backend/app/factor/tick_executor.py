from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

from .graph import FactorGraph
from .registry import FactorRegistry
from .runtime_config import FactorSettings
from .runtime_contract import FactorRuntimeContext
from .store import FactorEventWrite
from .pen import PivotMajorPoint

_DefaultFactory = Callable[[], Any]
_AliasSpec = tuple[str, str, _DefaultFactory]

_ALIAS_BY_FIELD: dict[str, _AliasSpec] = {
    "effective_pivots": ("pivot", "effective_pivots", list),
    "last_major_idx": ("pivot", "last_major_idx", lambda: None),
    "major_candidates": ("pivot", "major_candidates", list),
    "confirmed_pens": ("pen", "confirmed_pens", list),
    "new_confirmed_pen_payloads": ("pen", "new_confirmed_pen_payloads", list),
    "zhongshu_state": ("zhongshu", "payload", dict),
    "formed_entries": ("zhongshu", "formed_entries", list),
    "anchor_current_ref": ("anchor", "current_ref", lambda: None),
    "anchor_strength": ("anchor", "strength", lambda: None),
    "best_strong_pen_ref": ("anchor", "best_strong_pen_ref", lambda: None),
    "best_strong_pen_strength": ("anchor", "best_strong_pen_strength", lambda: None),
    "baseline_anchor_strength": ("anchor", "baseline_strength", lambda: None),
    "sr_major_pivots": ("sr", "major_pivots", list),
    "sr_snapshot": ("sr", "snapshot", dict),
}


@dataclass
class FactorTickState:
    visible_time: int
    tf_s: int
    settings: FactorSettings
    candles: list[Any]
    time_to_idx: dict[int, int]
    events: list[FactorEventWrite]
    factor_states: dict[str, dict[str, Any]]

    _direct_fields = {
        "visible_time",
        "tf_s",
        "settings",
        "candles",
        "time_to_idx",
        "events",
        "factor_states",
    }

    def factor_state(self, factor_name: str) -> dict[str, Any]:
        name = str(factor_name or "").strip()
        if not name:
            raise RuntimeError("factor_state_empty_name")
        state = self.factor_states.get(name)
        if state is None:
            state = {}
            self.factor_states[name] = state
        return state

    def __getattr__(self, name: str) -> Any:
        alias = _ALIAS_BY_FIELD.get(name)
        if alias is None:
            raise AttributeError(name)
        factor_name, field_name, default_factory = alias
        state = self.factor_state(factor_name)
        if field_name not in state:
            state[field_name] = default_factory()
        return state[field_name]

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._direct_fields:
            object.__setattr__(self, name, value)
            return
        alias = _ALIAS_BY_FIELD.get(name)
        if alias is None:
            object.__setattr__(self, name, value)
            return
        factor_name, field_name, _ = alias
        self.factor_state(factor_name)[field_name] = value


@dataclass(frozen=True)
class FactorTickExecutionResult:
    events: list[FactorEventWrite]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None
    sr_major_pivots: list[dict[str, Any]]
    sr_snapshot: dict[str, Any]
    factor_states: dict[str, dict[str, Any]]


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
    factor_states: dict[str, dict[str, Any]] | None = None


def _copy_factor_states(raw: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for factor_name, payload in (raw or {}).items():
        name = str(factor_name or "").strip()
        if not name:
            continue
        if not isinstance(payload, dict):
            continue
        out[name] = dict(payload)
    return out


def _seed_legacy_factor_state(
    *,
    request: FactorTickRunRequest,
    factor_states: dict[str, dict[str, Any]],
) -> None:
    pivot_state = factor_states.setdefault("pivot", {})
    pivot_state.setdefault("effective_pivots", request.effective_pivots)
    pivot_state.setdefault("last_major_idx", request.last_major_idx)

    pen_state = factor_states.setdefault("pen", {})
    pen_state.setdefault("confirmed_pens", request.confirmed_pens)

    zhongshu_state = factor_states.setdefault("zhongshu", {})
    zhongshu_state.setdefault("payload", request.zhongshu_state)

    anchor_state = factor_states.setdefault("anchor", {})
    anchor_state.setdefault("current_ref", request.anchor_current_ref)
    anchor_state.setdefault("strength", request.anchor_strength)

    sr_state = factor_states.setdefault("sr", {})
    sr_state.setdefault("major_pivots", [])
    sr_state.setdefault("snapshot", {})


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
        factor_states = _copy_factor_states(request.factor_states)
        _seed_legacy_factor_state(request=request, factor_states=factor_states)

        tick_state = FactorTickState(
            visible_time=0,
            tf_s=int(request.tf_s),
            settings=request.settings,
            candles=request.candles,
            time_to_idx=request.time_to_idx,
            events=out_events,
            factor_states=factor_states,
        )

        for visible_time in request.process_times:
            tick_state.visible_time = int(visible_time)
            tick_state.major_candidates = []
            tick_state.new_confirmed_pen_payloads = []
            tick_state.formed_entries = []
            tick_state.best_strong_pen_ref = None
            tick_state.best_strong_pen_strength = None
            current_strength = tick_state.anchor_strength
            tick_state.baseline_anchor_strength = (
                float(current_strength) if current_strength is not None else None
            )
            self.run_tick_steps(series_id=request.series_id, state=tick_state)

        return FactorTickExecutionResult(
            events=out_events,
            effective_pivots=cast(list[PivotMajorPoint], tick_state.effective_pivots),
            confirmed_pens=cast(list[dict[str, Any]], tick_state.confirmed_pens),
            zhongshu_state=cast(dict[str, Any], tick_state.zhongshu_state),
            anchor_current_ref=cast(dict[str, Any] | None, tick_state.anchor_current_ref),
            anchor_strength=cast(float | None, tick_state.anchor_strength),
            last_major_idx=cast(int | None, tick_state.last_major_idx),
            sr_major_pivots=cast(list[dict[str, Any]], tick_state.sr_major_pivots),
            sr_snapshot=cast(dict[str, Any], tick_state.sr_snapshot),
            factor_states=factor_states,
        )
