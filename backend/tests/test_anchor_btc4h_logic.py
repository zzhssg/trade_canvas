from __future__ import annotations

import unittest

from backend.app.anchor_semantics import build_anchor_history_from_switches
from backend.app.factor_processors import AnchorProcessor


class AnchorBtc4hLogicTests(unittest.TestCase):
    # UTC timestamps for the BTC 4h case:
    # - 2025-04-07 04:00:00
    # - 2025-06-22 20:00:00 (Asia/Shanghai date is 2025-06-23)
    # - 2025-10-27 04:00:00
    FIRST_ANCHOR_START = 1743998400
    SECOND_ANCHOR_START = 1750622400
    THIRD_ANCHOR_START = 1761537600
    FOURTH_CANDIDATE_START = 1768435200  # 2026-01-15 00:00:00

    def test_btc4h_first_three_anchors_follow_switch_rules(self) -> None:
        switches = [
            {
                "switch_time": 1748649600,  # 2025-05-31
                "reason": "strong_pen",
                "new_anchor": {
                    "kind": "confirmed",
                    "start_time": self.FIRST_ANCHOR_START,
                    "end_time": 1747929600,
                    "direction": 1,
                },
            },
            {
                "switch_time": 1757419200,  # 2025-09-09
                "reason": "zhongshu_entry",
                "new_anchor": {
                    "kind": "confirmed",
                    "start_time": self.SECOND_ANCHOR_START,
                    "end_time": 1752465600,
                    "direction": 1,
                },
            },
            {
                "switch_time": 1763409600,  # 2025-11-17
                "reason": "strong_pen",
                "new_anchor": {
                    "kind": "candidate",
                    "start_time": self.THIRD_ANCHOR_START,
                    "end_time": 1763409600,
                    "direction": -1,
                },
            },
        ]

        anchors, filtered = build_anchor_history_from_switches(switches)
        self.assertEqual(len(anchors), 3)
        self.assertEqual(len(filtered), 3)
        self.assertEqual([int(a["start_time"]) for a in anchors], [self.FIRST_ANCHOR_START, self.SECOND_ANCHOR_START, self.THIRD_ANCHOR_START])
        self.assertEqual(str(filtered[1]["reason"]), "zhongshu_entry")
        # 2025-08-14 pen start should not appear as an anchor in this case.
        self.assertNotIn(1755129600, [int(a["start_time"]) for a in anchors])

    def test_btc4h_fourth_anchor_switches_when_2026_01_15_pen_breaks_strength(self) -> None:
        processor = AnchorProcessor()
        old_anchor = {
            "kind": "candidate",
            "start_time": self.THIRD_ANCHOR_START,
            "end_time": 1763726400,
            "direction": -1,
        }
        baseline_strength = 35800.0
        candidate_pen = {
            "start_time": self.FOURTH_CANDIDATE_START,
            "end_time": 1768780800,
            "start_price": 98000.0,
            "end_price": 56000.0,
            "direction": -1,
        }

        new_ref, new_strength = processor.maybe_pick_stronger_pen(
            candidate_pen=candidate_pen,
            kind="candidate",
            baseline_anchor_strength=baseline_strength,
            current_best_ref=None,
            current_best_strength=None,
        )
        self.assertIsNotNone(new_ref)
        self.assertIsNotNone(new_strength)
        assert new_ref is not None
        assert new_strength is not None
        self.assertGreater(float(new_strength), float(baseline_strength))

        switch_event, current_ref, current_strength = processor.apply_strong_pen_switch(
            series_id="binance:spot:BTC/USDT:4h",
            switch_time=1768780800,
            old_anchor=old_anchor,
            new_anchor=dict(new_ref),
            new_anchor_strength=float(new_strength),
        )
        self.assertIsNotNone(switch_event)
        assert switch_event is not None
        payload = switch_event.payload or {}
        self.assertEqual(str(dict(payload).get("reason")), "strong_pen")
        self.assertIsNotNone(current_ref)
        assert current_ref is not None
        self.assertEqual(int(current_ref.get("start_time") or 0), self.FOURTH_CANDIDATE_START)
        self.assertIsNotNone(current_strength)
        assert current_strength is not None
        self.assertGreater(float(current_strength), float(baseline_strength))


if __name__ == "__main__":
    unittest.main()
