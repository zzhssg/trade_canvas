from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.core.schemas import CandleClosed
from backend.app.storage.candle_store import CandleStore


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
        os.environ.pop("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL", None)
        os.environ.pop("TRADE_CANVAS_MARKET_HISTORY_SOURCE", None)
        os.environ.pop("TRADE_CANVAS_FREQTRADE_DATADIR", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_CCXT_BACKFILL", None)

    @staticmethod
    def _write_feather(path: Path, *, n: int, freq: str) -> None:
        start = pd.Timestamp("2024-01-01T00:00:00Z")
        dates = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
        df = pd.DataFrame(
            {
                "date": dates,
                "open": [1.0 + i for i in range(n)],
                "high": [1.1 + i for i in range(n)],
                "low": [0.9 + i for i in range(n)],
                "close": [1.05 + i for i in range(n)],
                "volume": [100.0 + i for i in range(n)],
            }
        )
        df.to_feather(path)

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

    def test_get_market_candles_auto_backfills_non_whitelist_series(self) -> None:
        datadir = Path(self.tmpdir.name) / "datadir"
        datadir.mkdir(parents=True, exist_ok=True)
        self._write_feather(datadir / "SOL_USDT-1h.feather", n=4, freq="1h")

        os.environ["TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL"] = "1"
        os.environ["TRADE_CANVAS_MARKET_HISTORY_SOURCE"] = "freqtrade"
        os.environ["TRADE_CANVAS_FREQTRADE_DATADIR"] = str(datadir)
        os.environ["TRADE_CANVAS_ENABLE_CCXT_BACKFILL"] = "0"
        self.client.close()
        self.client = TestClient(create_app())

        series_id = "binance:spot:SOL/USDT:1h"
        resp = self.client.get("/api/market/candles", params={"series_id": series_id, "limit": 2000})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["series_id"], series_id)
        self.assertEqual(len(payload["candles"]), 4)
        self.assertEqual(payload["server_head_time"], payload["candles"][-1]["candle_time"])
