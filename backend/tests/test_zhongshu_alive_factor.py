from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class ZhongshuAliveFactorTests(unittest.TestCase):
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

    def test_zhongshu_alive_can_exist_before_first_dead(self) -> None:
        # Reuse the deterministic wave from test_zhongshu_dead_factor; it eventually yields a dead zhongshu.
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # Before death_time visibility (around 1260 for this fixture), we should be able to see an alive zhongshu snapshot.
        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 1140})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertIn("zhongshu", payload["factors"], "expected zhongshu factor to be present via head.alive")
        zs = payload["snapshots"]["zhongshu"]
        head = zs.get("head") or {}
        alive = head.get("alive") or []
        self.assertEqual(len(alive), 1, "expected a single alive zhongshu snapshot")
        item = alive[0]
        self.assertIsNone(item.get("death_time"))
        self.assertIn(int(item.get("entry_direction") or 0), {-1, 1})
        self.assertEqual(int(item.get("visible_time") or 0), int(payload["at_time"]))
        self.assertLessEqual(int(item.get("formed_time") or 0), int(payload["at_time"]))


if __name__ == "__main__":
    unittest.main()
