from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class MarketCandlesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)

        self.store = CandleStore(db_path=self.db_path)
        self.series_id = "binance:futures:BTC/USDT:1m"
        for t in (100, 160, 220):
            self.store.upsert_closed(
                self.series_id,
                CandleClosed(candle_time=t, open=1, high=2, low=0.5, close=1.5, volume=10),
            )

        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)

    def test_get_without_since_returns_tail_in_ascending_order(self) -> None:
        resp = self.client.get("/api/market/candles", params={"series_id": self.series_id, "limit": 2})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["server_head_time"], 220)
        self.assertEqual([c["candle_time"] for c in payload["candles"]], [160, 220])

    def test_get_with_since_is_exclusive(self) -> None:
        resp = self.client.get(
            "/api/market/candles",
            params={"series_id": self.series_id, "since": 160, "limit": 10},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual([c["candle_time"] for c in payload["candles"]], [220])

    def test_get_whitelist_endpoint(self) -> None:
        resp = self.client.get("/api/market/whitelist")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("series_ids", payload)
