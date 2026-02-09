from __future__ import annotations

import json
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
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_FACTOR_LOGIC_VERSION",
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

    def test_factor_slices_read_path_rebuilds_when_fingerprint_mismatched(self) -> None:
        base = 60
        prices = [1, 2, 3, 4, 5, 6]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO factor_events(series_id, factor_name, candle_time, kind, event_key, payload_json, created_at_ms)
                VALUES (?, 'zhongshu', ?, 'zhongshu.dead', ?, ?, 0)
                """,
                (
                    self.series_id,
                    int(times[-1]),
                    "test:stale-zhongshu",
                    json.dumps(
                        {
                            "start_time": 60,
                            "end_time": 120,
                            "zg": 5.0,
                            "zd": 4.0,
                            "entry_direction": 1,
                            "formed_time": 180,
                            "death_time": 240,
                            "visible_time": int(times[-1]),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()

        before = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(before.status_code, 200, before.text)
        self.assertIn("zhongshu", before.json()["factors"])

        os.environ["TRADE_CANVAS_FACTOR_LOGIC_VERSION"] = "force-rebuild-for-read-path"
        after = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(after.status_code, 200, after.text)
        self.assertNotIn("zhongshu", after.json()["factors"])
        os.environ.pop("TRADE_CANVAS_FACTOR_LOGIC_VERSION", None)


if __name__ == "__main__":
    unittest.main()
