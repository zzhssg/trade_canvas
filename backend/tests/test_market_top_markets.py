from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.market.list import _exchangeinfo_ttl_s, _futures_base_url, _spot_base_url, _ticker_ttl_s


class MarketTopMarketsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")

        # Make caching stable in tests.
        os.environ["TRADE_CANVAS_BINANCE_EXCHANGEINFO_TTL_S"] = "3600"
        os.environ["TRADE_CANVAS_BINANCE_TICKER_TTL_S"] = "3600"

        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_BINANCE_EXCHANGEINFO_TTL_S",
            "TRADE_CANVAS_BINANCE_TICKER_TTL_S",
        ):
            os.environ.pop(key, None)

    def test_spot_top_markets_filters_quote_and_sorts(self) -> None:
        spot_exchange_info = {
            "symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"},
                {"symbol": "ETHUSDT", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT"},
                {"symbol": "XRPFDUSD", "status": "TRADING", "baseAsset": "XRP", "quoteAsset": "FDUSD"},
                {"symbol": "BADUSDT", "status": "BREAK", "baseAsset": "BAD", "quoteAsset": "USDT"},
            ]
        }
        spot_tickers = [
            {"symbol": "BTCUSDT", "lastPrice": "100", "quoteVolume": "1000", "priceChangePercent": "1.5"},
            {"symbol": "ETHUSDT", "lastPrice": "10", "quoteVolume": "2000", "priceChangePercent": "-2.0"},
            {"symbol": "XRPFDUSD", "lastPrice": "1", "quoteVolume": "999999", "priceChangePercent": "0.1"},
        ]

        def fake_fetch(url: str, *, timeout_s: float = 5.0):
            if url.endswith("/api/v3/exchangeInfo"):
                return spot_exchange_info
            if url.endswith("/api/v3/ticker/24hr"):
                return spot_tickers
            raise AssertionError(f"unexpected url: {url}")

        with patch("backend.app.market.list._fetch_json", side_effect=fake_fetch):
            resp = self.client.get(
                "/api/market/top_markets",
                params={"exchange": "binance", "market": "spot", "quote_asset": "USDT", "limit": 2, "force": True},
            )
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertEqual(payload["exchange"], "binance")
            self.assertEqual(payload["market"], "spot")
            self.assertEqual(payload["quote_asset"], "USDT")
            self.assertEqual([i["symbol_id"] for i in payload["items"]], ["ETHUSDT", "BTCUSDT"])

    def test_futures_top_markets_only_perpetual(self) -> None:
        futures_exchange_info = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "BTCUSDT_230329",
                    "status": "TRADING",
                    "contractType": "CURRENT_QUARTER",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                },
            ]
        }
        futures_tickers = [
            {"symbol": "BTCUSDT", "lastPrice": "100", "quoteVolume": "1000", "priceChangePercent": "1.5"},
            {"symbol": "BTCUSDT_230329", "lastPrice": "100", "quoteVolume": "9999", "priceChangePercent": "1.5"},
        ]

        def fake_fetch(url: str, *, timeout_s: float = 5.0):
            if url.endswith("/fapi/v1/exchangeInfo"):
                return futures_exchange_info
            if url.endswith("/fapi/v1/ticker/24hr"):
                return futures_tickers
            raise AssertionError(f"unexpected url: {url}")

        with patch("backend.app.market.list._fetch_json", side_effect=fake_fetch):
            resp = self.client.get(
                "/api/market/top_markets",
                params={"exchange": "binance", "market": "futures", "quote_asset": "USDT", "limit": 20, "force": True},
            )
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertEqual([i["symbol_id"] for i in payload["items"]], ["BTCUSDT"])

    def test_cache_short_circuits_upstream_calls(self) -> None:
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

        with patch("backend.app.market.list._fetch_json", side_effect=fake_fetch):
            resp1 = self.client.get(
                "/api/market/top_markets",
                params={"exchange": "binance", "market": "spot", "quote_asset": "USDT", "limit": 20, "force": True},
            )
            self.assertEqual(resp1.status_code, 200)

        with patch("backend.app.market.list._fetch_json", side_effect=RuntimeError("upstream down")):
            resp2 = self.client.get(
                "/api/market/top_markets",
                params={"exchange": "binance", "market": "spot", "quote_asset": "USDT", "limit": 20},
            )
            self.assertEqual(resp2.status_code, 200)
            self.assertTrue(resp2.json()["cached"])


def test_market_list_env_parsing_helpers(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_SPOT_BASE_URL", " https://spot.test ")
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_FUTURES_BASE_URL", " https://futures.test/ ")
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_EXCHANGEINFO_TTL_S", "bad")
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_TICKER_TTL_S", "0")

    assert _spot_base_url() == "https://spot.test"
    assert _futures_base_url() == "https://futures.test"
    assert _exchangeinfo_ttl_s() == 3600
    assert _ticker_ttl_s() == 1


if __name__ == "__main__":
    unittest.main()
