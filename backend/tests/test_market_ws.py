from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CandleClosed


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
        os.environ.pop("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL", None)

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
            if not t.is_alive():
                self.assertNotIn("msg", got, "unexpected extra ws message after capacity error")
            ws.close()
            t.join(timeout=1.0)
            self.assertNotIn("msg", got)

    def test_ws_subscribe_gap_backfill_enabled_rehydrates_missing_candles(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL"] = "1"
        series_gap = "binance:futures:ETH/USDT:1m"

        for t in (100, 220):
            self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": series_gap,
                    "candle": {"candle_time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )

        def fake_backfill(*, store, series_id, expected_next_time, actual_time):
            self.assertEqual(series_id, series_gap)
            self.assertEqual(expected_next_time, 160)
            self.assertEqual(actual_time, 220)
            with store.connect() as conn:
                store.upsert_closed_in_conn(
                    conn,
                    series_gap,
                    CandleClosed(candle_time=160, open=1, high=2, low=0.5, close=1.5, volume=10),
                )
                conn.commit()
            return 1

        with mock.patch("backend.app.market_runtime_builder.backfill_market_gap_best_effort", side_effect=fake_backfill) as patched:
            with self.client.websocket_connect("/ws/market") as ws:
                ws.send_json({"type": "subscribe", "series_id": series_gap, "since": 100, "supports_batch": True})
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "candles_batch")
                self.assertEqual([c["candle_time"] for c in msg.get("candles", [])], [160, 220])
                patched.assert_called_once()

    def test_ws_invalid_message_shape_and_type_return_bad_request(self) -> None:
        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json(["bad-envelope"])
            err_envelope = ws.receive_json()
            self.assertEqual(err_envelope, {"type": "error", "code": "bad_request", "message": "invalid message envelope"})

            ws.send_json({"series_id": self.series_id})
            err_missing_type = ws.receive_json()
            self.assertEqual(err_missing_type, {"type": "error", "code": "bad_request", "message": "missing message type"})

            ws.send_json({"type": "noop"})
            err_unknown = ws.receive_json()
            self.assertEqual(err_unknown, {"type": "error", "code": "bad_request", "message": "unknown message type: noop"})
