from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.factor_runtime_config import FactorSettings
from backend.app.factor_runtime_contract import FactorRuntimeContext
from backend.app.factor_store import FactorEventWrite
from backend.app.factor_tick_executor import FactorTickExecutor, FactorTickState


class _GraphStub:
    def __init__(self, topo_order: tuple[str, ...]) -> None:
        self.topo_order = topo_order


class _RegistryStub:
    def __init__(self, plugins: dict[str, object]) -> None:
        self._plugins = plugins

    def require(self, name: str) -> object:
        return self._plugins[name]


class _TickPlugin:
    def __init__(self, *, name: str, calls: list[tuple[str, int]], baselines: list[tuple[str, int, float | None]]) -> None:
        self.spec = SimpleNamespace(factor_name=name, depends_on=())
        self._name = name
        self._calls = calls
        self._baselines = baselines

    def run_tick(self, *, series_id: str, state: FactorTickState, runtime: FactorRuntimeContext) -> None:
        _ = runtime
        self._calls.append((self._name, int(state.visible_time)))
        self._baselines.append((self._name, int(state.visible_time), state.baseline_anchor_strength))
        state.events.append(
            FactorEventWrite(
                series_id=series_id,
                factor_name=self._name,
                candle_time=int(state.visible_time),
                kind=f"{self._name}.tick",
                event_key=f"{self._name}:{int(state.visible_time)}",
                payload={"visible_time": int(state.visible_time)},
            )
        )
        if self._name == "pivot":
            state.last_major_idx = int(state.visible_time)
            state.anchor_current_ref = {
                "kind": "confirmed",
                "start_time": int(state.visible_time),
                "end_time": int(state.visible_time),
                "direction": 1,
            }
        if self._name == "pen":
            state.anchor_strength = float(state.visible_time)


def test_tick_executor_run_incremental_preserves_order_and_state() -> None:
    calls: list[tuple[str, int]] = []
    baselines: list[tuple[str, int, float | None]] = []
    plugins = {
        "pivot": _TickPlugin(name="pivot", calls=calls, baselines=baselines),
        "pen": _TickPlugin(name="pen", calls=calls, baselines=baselines),
    }
    executor = FactorTickExecutor(
        graph=_GraphStub(("pivot", "pen")),  # type: ignore[arg-type]
        registry=_RegistryStub(plugins),  # type: ignore[arg-type]
        runtime=FactorRuntimeContext(anchor_processor=None),
    )

    out = executor.run_incremental(
        series_id="s",
        process_times=[60, 120],
        tf_s=60,
        settings=FactorSettings(),
        candles=[],
        time_to_idx={},
        effective_pivots=[],
        confirmed_pens=[],
        zhongshu_state={},
        anchor_current_ref=None,
        anchor_strength=10.0,
        last_major_idx=None,
    )

    assert calls == [("pivot", 60), ("pen", 60), ("pivot", 120), ("pen", 120)]
    assert [b for _, t, b in baselines if t == 60] == [10.0, 10.0]
    assert [b for _, t, b in baselines if t == 120] == [60.0, 60.0]
    assert out.last_major_idx == 120
    assert out.anchor_strength == 120.0
    assert isinstance(out.anchor_current_ref, dict)
    assert len(out.events) == 4
    assert [e.event_key for e in out.events] == ["pivot:60", "pen:60", "pivot:120", "pen:120"]


def test_tick_executor_run_tick_steps_fail_fast_when_hook_missing() -> None:
    class _PluginWithoutRunTick:
        spec = SimpleNamespace(factor_name="pivot", depends_on=())

    executor = FactorTickExecutor(
        graph=_GraphStub(("pivot",)),  # type: ignore[arg-type]
        registry=_RegistryStub({"pivot": _PluginWithoutRunTick()}),  # type: ignore[arg-type]
        runtime=FactorRuntimeContext(anchor_processor=None),
    )

    state = FactorTickState(
        visible_time=60,
        tf_s=60,
        settings=FactorSettings(),
        candles=[],
        time_to_idx={},
        events=[],
        effective_pivots=[],
        confirmed_pens=[],
        zhongshu_state={},
        anchor_current_ref=None,
        anchor_strength=None,
        last_major_idx=None,
        major_candidates=[],
        new_confirmed_pen_payloads=[],
        formed_entries=[],
        best_strong_pen_ref=None,
        best_strong_pen_strength=None,
        baseline_anchor_strength=None,
    )
    with pytest.raises(RuntimeError, match="factor_missing_run_tick:pivot"):
        executor.run_tick_steps(series_id="s", state=state)
