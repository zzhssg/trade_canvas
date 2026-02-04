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
        self.whitelist_path = Path(self.tmpdir.name) / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
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
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST", None)
        os.environ.pop("TRADE_CANVAS_ONDEMAND_MAX_JOBS", None)

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

    def test_ws_subscribe_batch_catchup_and_stream(self) -> None:
        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100, "supports_batch": True})

            msg1 = ws.receive_json()
            self.assertEqual(msg1["type"], "candles_batch")
            times = [c["candle_time"] for c in msg1.get("candles", [])]
            self.assertEqual(times, [160, 220])

            self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": self.series_id,
                    "candle": {"candle_time": 280, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )

            msg2 = ws.receive_json()
            self.assertEqual(msg2["type"], "candle_closed")
            self.assertEqual(msg2["candle"]["candle_time"], 280)

    def test_ws_subscribe_capacity_rejects_without_catchup(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ONDEMAND_MAX_JOBS"] = "1"

        series1 = self.series_id
        series2 = "binance:futures:ETH/USDT:1m"

        for t in (100, 160, 220):
            self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": series2,
                    "candle": {"candle_time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )

        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": series1, "since": 100})
            _ = ws.receive_json()
            _ = ws.receive_json()

            ws.send_json({"type": "subscribe", "series_id": series2, "since": 100})
            err = ws.receive_json()
            self.assertEqual(err["type"], "error")
            self.assertEqual(err["code"], "capacity")
            self.assertEqual(err.get("series_id"), series2)

            import threading

            got: dict[str, object] = {}

            def recv_one() -> None:
                try:
                    got["msg"] = ws.receive_json()
                except BaseException as e:
                    got["exc"] = e

            t = threading.Thread(target=recv_one, daemon=True)
            t.start()
            t.join(timeout=0.2)
            self.assertTrue(t.is_alive(), "unexpected extra ws message after capacity error")
            ws.close()
            t.join(timeout=1.0)
            self.assertNotIn("msg", got)
