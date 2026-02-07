from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class FactorSlicesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_REBUILD"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "200"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_FACTOR_REBUILD",
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
                "candle": {"candle_time": t, "open": price, "high": price, "low": price, "close": price, "volume": 10},
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_factor_slices_empty_before_any_candles(self) -> None:
        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 120})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertEqual(payload["factors"], [])
        self.assertEqual(payload["snapshots"], {})

    def test_factor_slices_pivot_available_at_visible_time(self) -> None:
        # With window_major=2 and a hill [1,2,5,2,1], the local max at t=180 becomes visible at t=300.
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # Before major visible_time (t=300), pivot.major should not be visible yet.
        res0 = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 240})
        self.assertEqual(res0.status_code, 200, res0.text)
        payload0 = res0.json()
        self.assertEqual(payload0["factors"], [])

        # At/after visible_time, pivot should appear.
        res1 = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 300})
        self.assertEqual(res1.status_code, 200, res1.text)
        payload1 = res1.json()
        self.assertIn("pivot", payload1["factors"])
        snap = payload1["snapshots"]["pivot"]
        self.assertEqual(snap["meta"]["factor_name"], "pivot")
        majors = snap["history"]["major"]
        self.assertTrue(any(m.get("pivot_time") == 180 and m.get("direction") == "resistance" for m in majors))

    def test_factor_slices_returns_409_when_logic_hash_stale(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE factor_series_state SET logic_hash = ? WHERE series_id = ?",
                ("stale_hash_for_test", self.series_id),
            )
            conn.commit()

        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(res.status_code, 409, res.text)
        self.assertIn("stale_factor_logic_hash", res.text)

    def test_factor_rebuild_repairs_stale_logic_hash(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE factor_series_state SET logic_hash = ? WHERE series_id = ?",
                ("stale_hash_for_rebuild", self.series_id),
            )
            conn.commit()

        stale = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(stale.status_code, 409, stale.text)

        rebuilt = self.client.post("/api/factor/rebuild", json={"series_id": self.series_id, "include_overlay": False})
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        body = rebuilt.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["series_id"], self.series_id)
        self.assertGreater(len(body["factor_logic_hash"]), 8)

        ok = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_factor_rebuild_returns_404_when_feature_disabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_REBUILD"] = "0"
        res = self.client.post("/api/factor/rebuild", json={"series_id": self.series_id, "include_overlay": False})
        self.assertEqual(res.status_code, 404, res.text)


if __name__ == "__main__":
    unittest.main()
