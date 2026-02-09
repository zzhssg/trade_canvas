from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketRuntimeRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.whitelist_path = Path(self.tmpdir.name) / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)

    def test_market_http_and_ws_still_work(self) -> None:
        for t in (100, 160, 220):
            res = self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": self.series_id,
                    "candle": {"candle_time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )
            self.assertEqual(res.status_code, 200)

        candles_res = self.client.get(
            "/api/market/candles",
            params={"series_id": self.series_id, "since": 100, "limit": 10},
        )
        self.assertEqual(candles_res.status_code, 200)
        payload = candles_res.json()
        self.assertEqual([c["candle_time"] for c in payload.get("candles", [])], [160, 220])

        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100})
            msg1 = ws.receive_json()
            msg2 = ws.receive_json()
            self.assertEqual([msg1["candle"]["candle_time"], msg2["candle"]["candle_time"]], [160, 220])
