from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class WorldDeltaPollApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        os.environ["TRADE_CANVAS_OVERLAY_WINDOW_CANDLES"] = "2000"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
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

    def test_poll_is_idempotent_when_cursor_does_not_advance(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/delta/poll", params={"series_id": self.series_id, "after_id": 0, "window_candles": 2000})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        next_id = int(payload["next_cursor"]["id"])
        self.assertGreaterEqual(next_id, 0)
        if payload["records"]:
            rec = payload["records"][0]
            self.assertIn("factor_slices", rec)
            fs = rec["factor_slices"]
            self.assertIsNotNone(fs)
            self.assertEqual(fs["series_id"], self.series_id)
            self.assertEqual(int(fs["at_time"]), int(rec["to_candle_time"]))
            self.assertEqual(fs["candle_id"], rec["to_candle_id"])

        # Poll again from the returned cursor: should return no records and cursor stays.
        res2 = self.client.get(
            "/api/delta/poll",
            params={"series_id": self.series_id, "after_id": next_id, "window_candles": 2000},
        )
        self.assertEqual(res2.status_code, 200, res2.text)
        payload2 = res2.json()
        self.assertEqual(payload2["records"], [])
        self.assertEqual(int(payload2["next_cursor"]["id"]), next_id)


if __name__ == "__main__":
    unittest.main()
