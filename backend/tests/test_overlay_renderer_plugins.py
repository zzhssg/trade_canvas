from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.app.factor.graph import FactorGraph, FactorSpec
from backend.app.factor.plugin_registry import FactorPluginRegistry
from backend.app.overlay.renderer_plugins import (
    MarkerOverlayRenderer,
    OverlayEventBucketSpec,
    OverlayRenderContext,
    PenOverlayRenderer,
    SrOverlayRenderer,
    StructureOverlayRenderer,
    build_default_overlay_render_plugins,
    build_overlay_event_bucket_config,
    collect_overlay_event_buckets,
)


def _ctx(
    *,
    to_time: int = 200,
    cutoff_time: int = 100,
    pivot_major: list[dict] | None = None,
    pivot_minor: list[dict] | None = None,
    pen_confirmed: list[dict] | None = None,
    zhongshu_dead: list[dict] | None = None,
    anchor_switches: list[dict] | None = None,
    sr_snapshots: list[dict] | None = None,
) -> OverlayRenderContext:
    buckets = {
        "pivot_major": list(pivot_major or []),
        "pivot_minor": list(pivot_minor or []),
        "pen_confirmed": list(pen_confirmed or []),
        "zhongshu_dead": list(zhongshu_dead or []),
        "anchor_switches": list(anchor_switches or []),
        "sr_snapshots": list(sr_snapshots or []),
    }
    return OverlayRenderContext(
        series_id="binance:futures:BTC/USDT:1m",
        to_time=int(to_time),
        cutoff_time=int(cutoff_time),
        window_candles=2000,
        candles=[],
        buckets=buckets,
    )


class OverlayRendererPluginTests(unittest.TestCase):
    def test_default_plugins_are_graph_ready(self) -> None:
        plugins = build_default_overlay_render_plugins()
        reg = FactorPluginRegistry(list(plugins))
        graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in reg.specs()])
        self.assertEqual(graph.topo_order, ("overlay.marker", "overlay.pen", "overlay.structure", "overlay.sr"))

    def test_overlay_bucket_config_is_built_from_plugin_specs(self) -> None:
        plugins = build_default_overlay_render_plugins()
        by_kind, sort_keys, bucket_names = build_overlay_event_bucket_config(plugins)
        self.assertEqual(by_kind[("pivot", "pivot.major")], "pivot_major")
        self.assertEqual(by_kind[("anchor", "anchor.switch")], "anchor_switches")
        self.assertEqual(by_kind[("sr", "sr.snapshot")], "sr_snapshots")
        self.assertEqual(sort_keys["pen_confirmed"], ("visible_time", "start_time"))
        self.assertIn("zhongshu_dead", bucket_names)
        self.assertIn("sr_snapshots", bucket_names)

    def test_overlay_bucket_config_rejects_conflicts(self) -> None:
        class _PluginA:
            spec = SimpleNamespace(factor_name="overlay.a", depends_on=())
            bucket_specs = (OverlayEventBucketSpec(factor_name="pivot", event_kind="pivot.major", bucket_name="a"),)

            def render(self, *, ctx: OverlayRenderContext):
                _ = ctx
                return None

        class _PluginB:
            spec = SimpleNamespace(factor_name="overlay.b", depends_on=())
            bucket_specs = (OverlayEventBucketSpec(factor_name="pivot", event_kind="pivot.major", bucket_name="b"),)

            def render(self, *, ctx: OverlayRenderContext):
                _ = ctx
                return None

        with self.assertRaises(RuntimeError) as ctx:
            build_overlay_event_bucket_config((_PluginA(), _PluginB()))  # type: ignore[arg-type]
        self.assertIn("overlay_bucket_conflict:pivot:pivot.major", str(ctx.exception))

    def test_collect_overlay_event_buckets_applies_sort_keys(self) -> None:
        rows = [
            SimpleNamespace(
                factor_name="pen",
                kind="pen.confirmed",
                candle_time=300,
                payload={"visible_time": 300, "start_time": 180, "end_time": 240},
            ),
            SimpleNamespace(
                factor_name="pen",
                kind="pen.confirmed",
                candle_time=240,
                payload={"visible_time": 240, "start_time": 120, "end_time": 180},
            ),
        ]
        buckets = collect_overlay_event_buckets(
            rows=rows,
            event_bucket_by_kind={("pen", "pen.confirmed"): "pen_confirmed"},
            event_bucket_sort_keys={"pen_confirmed": ("visible_time", "start_time")},
            event_bucket_names=("pen_confirmed",),
        )
        self.assertEqual([int(item["visible_time"]) for item in buckets["pen_confirmed"]], [240, 300])

    def test_marker_renderer_emits_pivot_and_anchor_markers(self) -> None:
        renderer = MarkerOverlayRenderer()
        rendered = renderer.render(
            ctx=_ctx(
                pivot_major=[{"pivot_time": 120, "visible_time": 150, "direction": "resistance", "window": 5}],
                pivot_minor=[{"pivot_time": 140, "visible_time": 145, "direction": "support", "window": 3}],
                anchor_switches=[{"switch_time": 180, "reason": "strong_pen", "new_anchor": {"direction": 1}}],
            )
        )
        self.assertEqual(len(rendered.marker_defs), 3)
        ids = [row[0] for row in rendered.marker_defs]
        self.assertIn("pivot.major:120:resistance:5", ids)
        self.assertIn("pivot.minor:140:support:3", ids)
        self.assertIn("anchor.switch:180:1:strong_pen", ids)

    def test_pen_renderer_builds_confirmed_polyline(self) -> None:
        renderer = PenOverlayRenderer()
        rendered = renderer.render(
            ctx=_ctx(
                pen_confirmed=[
                    {"start_time": 120, "end_time": 150, "start_price": 10.0, "end_price": 11.0, "visible_time": 160},
                    {"start_time": 150, "end_time": 180, "start_price": 11.0, "end_price": 9.0, "visible_time": 190},
                ]
            )
        )
        self.assertEqual(int(rendered.pen_points_count), 3)
        self.assertTrue(rendered.polyline_defs)
        instruction_id, visible_time, payload = rendered.polyline_defs[0]
        self.assertEqual(str(instruction_id), "pen.confirmed")
        self.assertEqual(int(visible_time), 200)
        self.assertEqual(str(payload.get("feature")), "pen.confirmed")
        points = payload.get("points")
        self.assertIsInstance(points, list)
        if not isinstance(points, list):
            self.fail("pen points should be list")
        self.assertEqual(len(points), 3)

    def test_structure_renderer_handles_empty_inputs(self) -> None:
        renderer = StructureOverlayRenderer()
        rendered = renderer.render(ctx=_ctx())
        self.assertEqual(rendered.polyline_defs, [])

    def test_structure_renderer_keeps_anchor_current_when_switch_exists(self) -> None:
        renderer = StructureOverlayRenderer()
        candles = [
            SimpleNamespace(candle_time=120, open=10, high=11, low=9, close=10, volume=1),
            SimpleNamespace(candle_time=180, open=10, high=12, low=9, close=11, volume=1),
        ]
        rendered = renderer.render(
            ctx=OverlayRenderContext(
                series_id="binance:futures:BTC/USDT:1m",
                to_time=180,
                cutoff_time=60,
                window_candles=2000,
                candles=candles,
                buckets={
                    "pen_confirmed": [
                        {
                            "start_time": 120,
                            "end_time": 180,
                            "start_price": 10.0,
                            "end_price": 11.0,
                            "direction": 1,
                            "visible_time": 180,
                        }
                    ],
                    "anchor_switches": [
                        {
                            "switch_time": 180,
                            "new_anchor": {"kind": "confirmed", "start_time": 120, "end_time": 180, "direction": 1},
                        }
                    ],
                },
            )
        )
        anchor_current = next((row for row in rendered.polyline_defs if row[0] == "anchor.current"), None)
        self.assertIsNotNone(anchor_current)
        if anchor_current is None:
            return
        self.assertEqual(str(anchor_current[2].get("lineStyle") or "solid"), "solid")

    def test_structure_renderer_prefers_candidate_anchor_when_switch_pointer_is_stale(self) -> None:
        renderer = StructureOverlayRenderer()
        candles = [
            SimpleNamespace(candle_time=120, open=10, high=10.5, low=9.8, close=10.2, volume=1),
            SimpleNamespace(candle_time=180, open=10.2, high=11.2, low=10.1, close=11.0, volume=1),
            SimpleNamespace(candle_time=240, open=11.0, high=11.1, low=8.0, close=8.2, volume=1),
        ]
        rendered = renderer.render(
            ctx=OverlayRenderContext(
                series_id="binance:futures:BTC/USDT:1m",
                to_time=240,
                cutoff_time=60,
                window_candles=2000,
                candles=candles,
                buckets={
                    "pen_confirmed": [
                        {
                            "start_time": 120,
                            "end_time": 180,
                            "start_price": 10.0,
                            "end_price": 11.0,
                            "direction": 1,
                            "visible_time": 180,
                        }
                    ],
                    "anchor_switches": [
                        {
                            "switch_time": 180,
                            "new_anchor": {"kind": "candidate", "start_time": 120, "end_time": 180, "direction": 1},
                        }
                    ],
                },
            )
        )
        anchor_current = next((row for row in rendered.polyline_defs if row[0] == "anchor.current"), None)
        self.assertIsNotNone(anchor_current)
        if anchor_current is None:
            return
        points = anchor_current[2].get("points")
        self.assertIsInstance(points, list)
        if not isinstance(points, list) or len(points) < 2:
            self.fail("anchor.current points should include candidate start/end")
        self.assertEqual(int(points[0]["time"]), 180)
        self.assertEqual(int(points[1]["time"]), 240)
        self.assertEqual(str(anchor_current[2].get("lineStyle")), "dashed")

    def test_sr_renderer_builds_active_and_broken_lines(self) -> None:
        renderer = SrOverlayRenderer()
        rendered = renderer.render(
            ctx=_ctx(
                to_time=300,
                cutoff_time=120,
                sr_snapshots=[
                    {
                        "visible_time": 300,
                        "levels": [
                            {
                                "price": 110.0,
                                "status": "active",
                                "level_type": "resistance",
                                "first_time": 150,
                                "last_time": 240,
                            },
                            {
                                "price": 90.0,
                                "status": "broken",
                                "level_type": "support",
                                "first_time": 120,
                                "last_time": 210,
                                "death_time": 260,
                            },
                        ],
                    }
                ],
            )
        )
        self.assertEqual(len(rendered.polyline_defs), 2)
        features = [str(item[2].get("feature")) for item in rendered.polyline_defs]
        self.assertIn("sr.active", features)
        self.assertIn("sr.broken", features)


if __name__ == "__main__":
    unittest.main()
