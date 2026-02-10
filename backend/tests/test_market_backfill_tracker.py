from __future__ import annotations

import unittest

from backend.app.market_backfill_tracker import MarketBackfillProgressTracker


class MarketBackfillProgressTrackerTests(unittest.TestCase):
    def test_progress_moves_from_running_to_partial_success(self) -> None:
        tracker = MarketBackfillProgressTracker()
        series_id = "binance:futures:BTC/USDT:5m"
        tracker.begin(
            series_id=series_id,
            start_missing_seconds=600,
            start_missing_candles=2,
            reason="tail_coverage",
            now_time=1000,
        )
        snap_running = tracker.snapshot(series_id=series_id)
        self.assertEqual(snap_running.state, "running")
        self.assertEqual(snap_running.progress_pct, 0.0)

        tracker.succeed(
            series_id=series_id,
            current_missing_seconds=300,
            current_missing_candles=1,
            note="tail_coverage_partial",
            now_time=1010,
        )
        snap_done = tracker.snapshot(series_id=series_id)
        self.assertEqual(snap_done.state, "succeeded")
        self.assertAlmostEqual(float(snap_done.progress_pct or 0.0), 50.0, places=3)
        self.assertEqual(snap_done.current_missing_candles, 1)
        self.assertEqual(snap_done.note, "tail_coverage_partial")

    def test_fail_records_error(self) -> None:
        tracker = MarketBackfillProgressTracker()
        series_id = "binance:spot:ETH/USDT:1m"
        tracker.begin(
            series_id=series_id,
            start_missing_seconds=120,
            start_missing_candles=2,
            reason="tail_coverage",
            now_time=1000,
        )
        tracker.fail(
            series_id=series_id,
            current_missing_seconds=60,
            current_missing_candles=1,
            error="ccxt_failed",
            now_time=1015,
        )
        snap = tracker.snapshot(series_id=series_id)
        self.assertEqual(snap.state, "failed")
        self.assertEqual(snap.error, "ccxt_failed")
        self.assertEqual(snap.current_missing_seconds, 60)


if __name__ == "__main__":
    unittest.main()
