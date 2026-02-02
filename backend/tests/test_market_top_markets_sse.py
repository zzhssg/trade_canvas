from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketTopMarketsSseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in ("TRADE_CANVAS_DB_PATH", "TRADE_CANVAS_WHITELIST_PATH"):
            os.environ.pop(key, None)

    def test_sse_stream_emits_top_markets_event(self) -> None:
        spot_exchange_info = {
            "symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"},
            ]
        }
        spot_tickers = [
            {"symbol": "BTCUSDT", "lastPrice": "100", "quoteVolume": "1000", "priceChangePercent": "1.5"},
        ]

        def fake_fetch(url: str, *, timeout_s: float = 5.0):
            if url.endswith("/api/v3/exchangeInfo"):
                return spot_exchange_info
            if url.endswith("/api/v3/ticker/24hr"):
                return spot_tickers
            raise AssertionError(f"unexpected url: {url}")

        with patch("backend.app.market_list._fetch_json", side_effect=fake_fetch):
            resp = self.client.get(
                "/api/market/top_markets/stream",
                params={
                    "exchange": "binance",
                    "market": "spot",
                    "quote_asset": "USDT",
                    "limit": 20,
                    "interval_s": 0.2,
                    "max_events": 1,
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
            body = resp.text
            self.assertIn("event: top_markets", body)
            self.assertIn("\"symbol_id\":\"BTCUSDT\"", body)


if __name__ == "__main__":
    unittest.main()
