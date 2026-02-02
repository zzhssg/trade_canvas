from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketWebSocketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

        for t in (100, 160, 220):
            self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": self.series_id,
                    "candle": {"candle_time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)

    def test_ws_subscribe_catchup_and_stream(self) -> None:
        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100})

            msg1 = ws.receive_json()
            self.assertEqual(msg1["type"], "candle_closed")
            self.assertEqual(msg1["candle"]["candle_time"], 160)

            msg2 = ws.receive_json()
            self.assertEqual(msg2["type"], "candle_closed")
            self.assertEqual(msg2["candle"]["candle_time"], 220)

            self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": self.series_id,
                    "candle": {"candle_time": 280, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )

            msg3 = ws.receive_json()
            self.assertEqual(msg3["type"], "candle_closed")
            self.assertEqual(msg3["candle"]["candle_time"], 280)

