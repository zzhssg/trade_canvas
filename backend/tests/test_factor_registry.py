from __future__ import annotations

import unittest

from backend.app.factor_graph import FactorGraph, FactorSpec
from backend.app.factor_processors import (
    AnchorProcessor,
    PenProcessor,
    PivotProcessor,
    ZhongshuProcessor,
    build_default_factor_processors,
    build_default_slice_bucket_specs,
)
from backend.app.factor_registry import FactorRegistry, FactorRegistryError
from backend.app.pen import ConfirmedPen, PivotMajorPoint
from backend.app.zhongshu import ZhongshuDead


class FactorRegistryTests(unittest.TestCase):
    def test_registry_rejects_duplicate_factor_name(self) -> None:
        with self.assertRaises(FactorRegistryError) as ctx:
            FactorRegistry([PivotProcessor(), PivotProcessor()])
        self.assertIn("duplicate_factor:pivot", str(ctx.exception))

    def test_registry_require_missing_factor(self) -> None:
        reg = FactorRegistry([PivotProcessor(), PenProcessor(), ZhongshuProcessor(), AnchorProcessor()])
        with self.assertRaises(FactorRegistryError) as ctx:
            reg.require("missing")
        self.assertIn("missing_factor:missing", str(ctx.exception))

    def test_registry_specs_can_build_graph(self) -> None:
        reg = FactorRegistry([PivotProcessor(), PenProcessor(), ZhongshuProcessor(), AnchorProcessor()])
        specs = [FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in reg.specs()]
        graph = FactorGraph(specs)
        self.assertEqual(graph.topo_order, ("pivot", "pen", "zhongshu", "anchor"))

    def test_default_processors_are_graph_ready(self) -> None:
        reg = FactorRegistry(build_default_factor_processors())
        self.assertEqual([s.factor_name for s in reg.specs()], ["pivot", "pen", "zhongshu", "anchor"])

    def test_default_slice_bucket_specs_are_unique_and_cover_anchor(self) -> None:
        specs = build_default_slice_bucket_specs()
        keys = [(s.factor_name, s.event_kind) for s in specs]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(("anchor", "anchor.switch"), keys)
        bucket_names = [s.bucket_name for s in specs]
        self.assertEqual(len(bucket_names), len(set(bucket_names)))

    def test_pivot_processor_builds_stable_event_keys(self) -> None:
        p = PivotMajorPoint(
            pivot_time=120,
            pivot_price=100.5,
            direction="resistance",
            visible_time=240,
            pivot_idx=10,
        )
        proc = PivotProcessor()
        major = proc.build_major_event(series_id="s", pivot=p, window=50)
        minor = proc.build_minor_event(series_id="s", pivot=p, window=5)
        self.assertEqual(major.event_key, "major:120:resistance:50")
        self.assertEqual(minor.event_key, "minor:120:resistance:5")
        self.assertEqual(major.payload["pivot_idx"], 10)

    def test_pen_processor_builds_stable_event_key(self) -> None:
        pen = ConfirmedPen(
            start_time=120,
            end_time=180,
            start_price=100.0,
            end_price=102.0,
            direction=1,
            visible_time=240,
            start_idx=20,
            end_idx=30,
        )
        event = PenProcessor().build_confirmed_event(series_id="s", pen=pen)
        self.assertEqual(event.event_key, "confirmed:120:180:1")
        self.assertEqual(event.payload["visible_time"], 240)

    def test_zhongshu_processor_builds_dead_event_key(self) -> None:
        dead = ZhongshuDead(
            start_time=120,
            end_time=200,
            zg=130.0,
            zd=110.0,
            entry_direction=1,
            formed_time=180,
            death_time=240,
            visible_time=240,
            formed_reason="pen_confirmed",
        )
        event = ZhongshuProcessor().build_dead_event(series_id="s", dead_event=dead)
        self.assertEqual(event.event_key, "dead:120:180:240:130.00000000:110.00000000:pen_confirmed")
        self.assertEqual(event.payload["formed_reason"], "pen_confirmed")

    def test_anchor_processor_builds_stable_switch_event_keys(self) -> None:
        proc = AnchorProcessor()
        old_ref = {"kind": "confirmed", "start_time": 120, "end_time": 180, "direction": 1}
        formed_entry = {"start_time": 180, "end_time": 240, "start_price": 110.0, "end_price": 125.0, "direction": 1}

        z_event, z_ref, z_strength = proc.apply_zhongshu_entry_switch(
            series_id="s",
            formed_entry=formed_entry,
            switch_time=300,
            old_anchor=old_ref,
        )
        self.assertIsNotNone(z_event)
        self.assertEqual(z_event.event_key, "zhongshu_entry:300:180:240:1")
        self.assertEqual(z_ref["kind"], "confirmed")
        self.assertGreater(z_strength, 0.0)

        strong_ref = {"kind": "candidate", "start_time": 240, "end_time": 300, "direction": -1}
        s_event, s_cur, s_strength = proc.apply_strong_pen_switch(
            series_id="s",
            switch_time=360,
            old_anchor=z_ref,
            new_anchor=strong_ref,
            new_anchor_strength=15.0,
        )
        self.assertIsNotNone(s_event)
        self.assertEqual(s_event.event_key, "strong_pen:360:candidate:240:300:-1")
        self.assertEqual(s_cur["kind"], "candidate")
        self.assertEqual(s_strength, 15.0)


if __name__ == "__main__":
    unittest.main()
