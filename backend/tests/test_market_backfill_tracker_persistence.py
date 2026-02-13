from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.market.backfill_tracker import MarketBackfillProgressTracker


class MarketBackfillProgressTrackerPersistenceTests(unittest.TestCase):
    def test_tracker_persists_state_and_restores_on_next_boot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "runtime_state" / "market_backfill_progress.json"
            series_id = "binance:futures:BTC/USDT:1m"

            tracker = MarketBackfillProgressTracker(state_path=state_path)
            tracker.begin(
                series_id=series_id,
                start_missing_seconds=300,
                start_missing_candles=5,
                reason="tail_coverage",
                now_time=1000,
            )
            tracker.succeed(
                series_id=series_id,
                current_missing_seconds=0,
                current_missing_candles=0,
                note="tail_coverage_done",
                now_time=1010,
            )

            self.assertTrue(state_path.exists())

            restored = MarketBackfillProgressTracker(state_path=state_path)
            snapshot = restored.snapshot(series_id=series_id)
            self.assertEqual(snapshot.state, "succeeded")
            self.assertEqual(snapshot.start_missing_seconds, 300)
            self.assertEqual(snapshot.current_missing_seconds, 0)
            self.assertEqual(snapshot.note, "tail_coverage_done")

    def test_tracker_ignores_broken_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "runtime_state" / "market_backfill_progress.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text("{broken-json", encoding="utf-8")
            tracker = MarketBackfillProgressTracker(state_path=state_path)
            snapshot = tracker.snapshot(series_id="binance:spot:ETH/USDT:5m")
            self.assertEqual(snapshot.state, "idle")


if __name__ == "__main__":
    unittest.main()
