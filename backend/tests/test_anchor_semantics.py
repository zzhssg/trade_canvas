from __future__ import annotations

import unittest

from backend.app.anchor_semantics import build_anchor_history_from_switches, should_append_switch


class AnchorSemanticsTests(unittest.TestCase):
    def test_same_start_switch_is_suppressed(self) -> None:
        old_anchor = {"kind": "confirmed", "start_time": 100, "end_time": 200, "direction": 1}
        new_anchor_same_start = {"kind": "confirmed", "start_time": 100, "end_time": 260, "direction": 1}
        new_anchor_new_start = {"kind": "confirmed", "start_time": 180, "end_time": 260, "direction": 1}

        self.assertFalse(should_append_switch(old_anchor=old_anchor, new_anchor=new_anchor_same_start))
        self.assertTrue(should_append_switch(old_anchor=old_anchor, new_anchor=new_anchor_new_start))

    def test_history_anchors_align_with_switches(self) -> None:
        switches = [
            {
                "switch_time": 120,
                "reason": "strong_pen",
                "new_anchor": {"kind": "confirmed", "start_time": 60, "end_time": 120, "direction": 1},
            },
            {
                "switch_time": 180,
                "reason": "strong_pen",
                "new_anchor": {"kind": "candidate", "start_time": 120, "end_time": 180, "direction": -1},
            },
        ]
        anchors, filtered = build_anchor_history_from_switches(switches)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(anchors[0], switches[0]["new_anchor"])
        self.assertEqual(anchors[1], switches[1]["new_anchor"])


if __name__ == "__main__":
    unittest.main()
