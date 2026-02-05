from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class E2EUserStoryFactorLedgerPenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
        ):
            os.environ.pop(k, None)

    def _ingest(self, t: int, price: float) -> None:
        res = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": t, "open": price, "high": price, "low": price, "close": price, "volume": 1},
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_user_story_factor_slices_includes_confirmed_pen(self) -> None:
        # Build a deterministic wave that yields alternating major pivots with window_major=2.
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # Before enough pivots are visible, no factors yet.
        res0 = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 240})
        self.assertEqual(res0.status_code, 200, res0.text)
        payload0 = res0.json()
        self.assertEqual(payload0["factors"], [])

        # After enough candles, pivot.major becomes visible; pen.confirmed requires at least 3 pivots.
        res1 = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 540})
        self.assertEqual(res1.status_code, 200, res1.text)
        payload1 = res1.json()
        self.assertIn("pivot", payload1["factors"])
        self.assertIn("pen", payload1["factors"])

        piv = payload1["snapshots"]["pivot"]
        self.assertGreaterEqual(len(piv["history"]["major"]), 1)

        pen = payload1["snapshots"]["pen"]
        confirmed = pen["history"]["confirmed"]
        self.assertGreaterEqual(len(confirmed), 1)
        for item in confirmed:
            self.assertLessEqual(int(item.get("visible_time") or 0), int(payload1["at_time"]))


if __name__ == "__main__":
    unittest.main()
