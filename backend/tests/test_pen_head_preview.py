from __future__ import annotations

from dataclasses import dataclass
import unittest

from backend.app.factor.slices import build_pen_head_preview


@dataclass(frozen=True)
class _Candle:
    candle_time: int
    high: float
    low: float


class PenHeadPreviewTests(unittest.TestCase):
    def test_preview_builds_extending_and_candidate_from_second_last_major(self) -> None:
        candles = [
            _Candle(candle_time=60, high=2.0, low=1.0),
            _Candle(candle_time=120, high=4.0, low=2.0),
            _Candle(candle_time=180, high=7.0, low=3.0),
            _Candle(candle_time=240, high=6.0, low=2.0),
            _Candle(candle_time=300, high=5.0, low=1.0),
            _Candle(candle_time=360, high=8.0, low=2.0),
            _Candle(candle_time=420, high=6.0, low=0.5),
            _Candle(candle_time=480, high=9.0, low=1.0),
        ]
        major = [
            {"pivot_time": 60, "pivot_price": 1.0, "direction": "support", "visible_time": 60},
            {"pivot_time": 180, "pivot_price": 7.0, "direction": "resistance", "visible_time": 180},
            {"pivot_time": 300, "pivot_price": 1.0, "direction": "support", "visible_time": 300},
        ]

        out = build_pen_head_preview(candles=candles, major_pivots=major, aligned_time=480)
        self.assertIn("extending", out)
        self.assertIn("candidate", out)

        extending = out["extending"]
        candidate = out["candidate"]

        self.assertEqual(int(extending["start_time"]), 180)
        self.assertEqual(int(extending["end_time"]), 420)
        self.assertEqual(int(extending["direction"]), -1)
        self.assertAlmostEqual(float(extending["start_price"]), 7.0, places=6)
        self.assertAlmostEqual(float(extending["end_price"]), 0.5, places=6)

        self.assertEqual(int(candidate["start_time"]), int(extending["end_time"]))
        self.assertEqual(int(candidate["end_time"]), 480)
        self.assertEqual(int(candidate["direction"]), 1)
        self.assertAlmostEqual(float(candidate["start_price"]), float(extending["end_price"]), places=6)
        self.assertAlmostEqual(float(candidate["end_price"]), 9.0, places=6)


if __name__ == "__main__":
    unittest.main()
