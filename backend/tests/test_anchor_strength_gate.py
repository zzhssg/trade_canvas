from __future__ import annotations

import unittest

from backend.app.factor_processor_anchor import AnchorProcessor


class AnchorStrengthGateTests(unittest.TestCase):
    def test_candidate_must_beat_baseline(self) -> None:
        self.assertTrue(AnchorProcessor.beats_anchor_strength(candidate_strength=20.0, baseline_anchor_strength=15.0))
        self.assertFalse(AnchorProcessor.beats_anchor_strength(candidate_strength=15.0, baseline_anchor_strength=15.0))
        self.assertFalse(AnchorProcessor.beats_anchor_strength(candidate_strength=14.9, baseline_anchor_strength=15.0))

    def test_no_baseline_allows_candidate(self) -> None:
        self.assertTrue(AnchorProcessor.beats_anchor_strength(candidate_strength=0.0, baseline_anchor_strength=None))


if __name__ == "__main__":
    unittest.main()
