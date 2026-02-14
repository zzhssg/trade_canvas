from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from backend.app.factor.ingest_outputs import HeadBuildState
from backend.app.factor.orchestrator import FactorOrchestrator, FactorSettings
from backend.app.factor.store import FactorEventRow, FactorStore
from backend.app.core.schemas import CandleClosed
from backend.app.storage.candle_store import CandleStore


class FactorOrchestratorSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.orchestrator = FactorOrchestrator(
            candle_store=CandleStore(self.db_path),
            factor_store=FactorStore(self.db_path),
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_FACTOR_LOGIC_VERSION",
        ):
            os.environ.pop(key, None)

    def _rebuild_orchestrator(
        self,
        *,
        settings: FactorSettings | None = None,
        ingest_enabled: bool = True,
        logic_version_override: str = "",
        fingerprint_rebuild_enabled: bool = True,
        factor_rebuild_keep_candles: int = 2000,
    ) -> None:
        self.orchestrator = FactorOrchestrator(
            candle_store=CandleStore(self.db_path),
            factor_store=FactorStore(self.db_path),
            settings=settings,
            ingest_enabled=ingest_enabled,
            logic_version_override=logic_version_override,
            fingerprint_rebuild_enabled=fingerprint_rebuild_enabled,
            factor_rebuild_keep_candles=factor_rebuild_keep_candles,
        )

    def test_load_settings_uses_constructor_settings(self) -> None:
        self._rebuild_orchestrator(
            settings=FactorSettings(
                pivot_window_major=3,
                pivot_window_minor=2,
                lookback_candles=1234,
                state_rebuild_event_limit=3200,
            )
        )
        settings = self.orchestrator._load_settings()
        self.assertEqual(settings.pivot_window_major, 3)
        self.assertEqual(settings.pivot_window_minor, 2)
        self.assertEqual(settings.lookback_candles, 1234)
        self.assertEqual(settings.state_rebuild_event_limit, 3200)

    def test_enabled_uses_constructor_flag(self) -> None:
        self._rebuild_orchestrator(ingest_enabled=False)
        self.assertFalse(self.orchestrator.enabled())

        self._rebuild_orchestrator(ingest_enabled=True)
        self.assertTrue(self.orchestrator.enabled())

    def test_fingerprint_includes_state_rebuild_event_limit(self) -> None:
        s1 = FactorSettings(state_rebuild_event_limit=50000)
        s2 = FactorSettings(state_rebuild_event_limit=80000)
        fp1 = self.orchestrator._build_series_fingerprint(series_id="binance:futures:BTC/USDT:1m", settings=s1)
        fp2 = self.orchestrator._build_series_fingerprint(series_id="binance:futures:BTC/USDT:1m", settings=s2)
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_includes_logic_version_override(self) -> None:
        self._rebuild_orchestrator(logic_version_override="v1")
        fp1 = self.orchestrator._build_series_fingerprint(
            series_id="binance:futures:BTC/USDT:1m",
            settings=FactorSettings(),
        )
        self._rebuild_orchestrator(logic_version_override="v2")
        fp2 = self.orchestrator._build_series_fingerprint(
            series_id="binance:futures:BTC/USDT:1m",
            settings=FactorSettings(),
        )
        self.assertNotEqual(fp1, fp2)

    def test_state_rebuild_uses_paged_scan_after_limit_hit(self) -> None:
        self._rebuild_orchestrator(
            settings=FactorSettings(
                pivot_window_major=1,
                pivot_window_minor=1,
                lookback_candles=100,
                state_rebuild_event_limit=1000,
            )
        )
        series_id = "binance:futures:BTC/USDT:1m"

        self.orchestrator._candle_store.upsert_closed(
            series_id,
            CandleClosed(candle_time=60, open=100, high=101, low=99, close=100, volume=1),
        )
        self.orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=60)

        self.orchestrator._candle_store.upsert_closed(
            series_id,
            CandleClosed(candle_time=120, open=100, high=101, low=99, close=100, volume=1),
        )

        fake_rows = [
            FactorEventRow(
                id=i + 1,
                series_id=series_id,
                factor_name="pivot",
                candle_time=60,
                kind="pivot.major",
                event_key=f"k:{i}",
                payload={},
            )
            for i in range(1000)
        ]
        with (
            patch.object(FactorStore, "get_events_between_times", return_value=fake_rows) as base_scan,
            patch.object(FactorStore, "iter_events_between_times_paged", return_value=iter(())) as paged_scan,
        ):
            self.orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=120)

        self.assertTrue(base_scan.called)
        self.assertTrue(paged_scan.called)

    def test_collect_rebuild_buckets_uses_plugin_collectors_and_sort(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        rows = [
            FactorEventRow(
                id=1,
                series_id=series_id,
                factor_name="pivot",
                candle_time=300,
                kind="pivot.major",
                event_key="a",
                payload={"pivot_time": 180, "visible_time": 300, "direction": "resistance", "pivot_price": 10.0},
            ),
            FactorEventRow(
                id=2,
                series_id=series_id,
                factor_name="pivot",
                candle_time=240,
                kind="pivot.major",
                event_key="b",
                payload={"pivot_time": 120, "visible_time": 240, "direction": "support", "pivot_price": 8.0},
            ),
            FactorEventRow(
                id=3,
                series_id=series_id,
                factor_name="pen",
                candle_time=300,
                kind="pen.confirmed",
                event_key="c",
                payload={"start_time": 120, "end_time": 180, "visible_time": 300, "direction": 1},
            ),
            FactorEventRow(
                id=4,
                series_id=series_id,
                factor_name="anchor",
                candle_time=360,
                kind="anchor.switch",
                event_key="d",
                payload={"switch_time": 360, "visible_time": 360},
            ),
        ]
        with patch.object(FactorStore, "get_events_between_times", return_value=rows):
            buckets = self.orchestrator._collect_rebuild_event_buckets(
                series_id=series_id,
                state_start=0,
                head_time=400,
                scan_limit=100,
            )

        pivot_events = buckets.events_by_factor["pivot"]
        self.assertEqual(len(pivot_events), 2)
        self.assertEqual(int(pivot_events[0]["visible_time"]), 240)
        self.assertEqual(int(pivot_events[1]["visible_time"]), 300)
        self.assertEqual(len(buckets.events_by_factor["pen"]), 1)
        self.assertEqual(len(buckets.events_by_factor["anchor"]), 1)

    def test_tick_steps_follow_graph_topo_order(self) -> None:
        calls: list[str] = []

        class _Plugin:
            def __init__(self, name: str) -> None:
                self.spec = SimpleNamespace(factor_name=name, depends_on=())
                self._name = name

            def run_tick(self, *, series_id: str, state: object, runtime: dict[str, Any]) -> None:
                _ = series_id
                _ = state
                _ = runtime
                calls.append(self._name)

        plugins = {name: _Plugin(name) for name in ("pivot", "pen", "zhongshu", "anchor", "sr")}
        self.orchestrator._graph = cast(Any, SimpleNamespace(topo_order=("pivot", "pen", "zhongshu", "anchor", "sr")))
        self.orchestrator._registry = cast(Any, SimpleNamespace(require=lambda name: plugins[name]))
        self.orchestrator._tick_runtime = cast(Any, {})
        self.orchestrator._run_tick_steps(series_id="s", state=SimpleNamespace())  # type: ignore[arg-type]
        self.assertEqual(calls, ["pivot", "pen", "zhongshu", "anchor", "sr"])

    def test_build_head_snapshots_uses_plugin_head_hooks(self) -> None:
        class _Plugin:
            def __init__(self, name: str) -> None:
                self.spec = SimpleNamespace(factor_name=name, depends_on=())
                self._name = name

            def build_head_snapshot(self, *, series_id: str, state: object, runtime: dict[str, Any]) -> dict[str, Any] | None:
                _ = series_id
                _ = state
                _ = runtime
                return {"name": self._name}

        plugins = {name: _Plugin(name) for name in ("pivot", "pen")}
        self.orchestrator._graph = cast(Any, SimpleNamespace(topo_order=("pivot", "pen")))
        self.orchestrator._registry = cast(Any, SimpleNamespace(require=lambda name: plugins[name]))
        self.orchestrator._tick_runtime = cast(Any, {})
        head_state = HeadBuildState(
            up_to=120,
            candles=[],
            effective_pivots=[],
            confirmed_pens=[],
            zhongshu_state={},
            anchor_current_ref=None,
            sr_major_pivots=[],
            sr_snapshot={},
        )
        out = self.orchestrator._build_head_snapshots(
            series_id="s",
            state=head_state,
        )
        self.assertEqual(out, {"pivot": {"name": "pivot"}, "pen": {"name": "pen"}})

    def test_tick_steps_fail_fast_when_plugin_missing_run_tick(self) -> None:
        class _PluginWithoutTick:
            def __init__(self) -> None:
                self.spec = SimpleNamespace(factor_name="pivot", depends_on=())

        self.orchestrator._graph = cast(Any, SimpleNamespace(topo_order=("pivot",)))
        self.orchestrator._registry = cast(Any, SimpleNamespace(require=lambda name: _PluginWithoutTick()))
        self.orchestrator._tick_runtime = cast(Any, {})
        with self.assertRaises(RuntimeError) as ctx:
            self.orchestrator._run_tick_steps(series_id="s", state=SimpleNamespace())  # type: ignore[arg-type]
        self.assertIn("factor_missing_run_tick:pivot", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
