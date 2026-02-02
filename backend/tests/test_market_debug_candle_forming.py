from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketDebugCandleFormingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)

    def test_debug_forming_ingest_404_when_disabled(self) -> None:
        client = TestClient(create_app())
        resp = client.post(
            "/api/market/ingest/candle_forming",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": 180, "open": 1, "high": 2, "low": 0.5, "close": 10, "volume": 10},
            },
        )
        self.assertEqual(resp.status_code, 404)

    def test_debug_forming_ingest_200_and_does_not_write_store(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = TestClient(create_app())
        resp = client.post(
            "/api/market/ingest/candle_forming",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": 180, "open": 1, "high": 2, "low": 0.5, "close": 10, "volume": 10},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        candles = client.get("/api/market/candles", params={"series_id": self.series_id, "limit": 10}).json()
        self.assertEqual(candles["candles"], [])
        self.assertIsNone(candles["server_head_time"])


if __name__ == "__main__":
    unittest.main()

