from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.core.schemas import CandleClosed


class MarketSyncE2EUserStoryTests(unittest.TestCase):
    """
    User story (E2E):
    1) Backend ingests CandleClosed via HTTP
    2) Client fetches candles via HTTP incremental API
    3) Client subscribes via WS and receives catchup + live updates
    4) Gap detection is emitted when expected_next_time is skipped
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ.pop("TRADE_CANVAS_ENABLE_PG_STORE", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_PG_ONLY", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_DSN", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_SCHEMA", None)

        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")

        self.client = TestClient(create_app())

        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL", None)
        os.environ.pop("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_CCXT_BACKFILL", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", None)
        os.environ.pop("TRADE_CANVAS_MARKET_HISTORY_SOURCE", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_PG_STORE", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_PG_ONLY", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_DSN", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_SCHEMA", None)

    def _ingest(self, candle_time: int) -> None:
        resp = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {
                    "candle_time": candle_time,
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 10.0,
                },
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_http_read_path_tail_and_head_time(self) -> None:
        for t in (100, 160, 220):
            self._ingest(t)

        resp = self.client.get("/api/market/candles", params={"series_id": self.series_id, "limit": 2})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertEqual(payload["server_head_time"], 220)
        self.assertEqual([c["candle_time"] for c in payload["candles"]], [160, 220])

        resp2 = self.client.get(
            "/api/market/candles",
            params={"series_id": self.series_id, "since": 160, "limit": 10},
        )
        self.assertEqual(resp2.status_code, 200)
        payload2 = resp2.json()
        self.assertEqual([c["candle_time"] for c in payload2["candles"]], [220])

    def test_http_read_live_tail_backfill_uses_ccxt_when_auto_tail_enabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL"] = "1"
        os.environ["TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES"] = "2"
        os.environ["TRADE_CANVAS_ENABLE_CCXT_BACKFILL"] = "1"
        os.environ.pop("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", None)
        os.environ["TRADE_CANVAS_MARKET_HISTORY_SOURCE"] = ""
        calls: list[tuple[int, int]] = []

        def fake_ccxt_backfill(*, candle_store, series_id, start_time, end_time, batch_limit=1000, ccxt_timeout_ms=10_000):
            _ = batch_limit
            _ = ccxt_timeout_ms
            self.assertEqual(series_id, self.series_id)
            calls.append((int(start_time), int(end_time)))
            with candle_store.connect() as conn:
                candle_store.upsert_closed_in_conn(
                    conn,
                    self.series_id,
                    CandleClosed(candle_time=int(start_time), open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                candle_store.upsert_closed_in_conn(
                    conn,
                    self.series_id,
                    CandleClosed(candle_time=int(end_time), open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                conn.commit()
            return 2

        with (
            mock.patch("backend.app.market_data.read_services.backfill_from_ccxt_range", side_effect=fake_ccxt_backfill),
            mock.patch("backend.app.market_data.read_services.time.time", return_value=121),
        ):
            self.client.close()
            with TestClient(create_app()) as client:
                resp = client.get("/api/market/candles", params={"series_id": self.series_id, "limit": 2})

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(calls, [(60, 120)])
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertTrue(len(payload["candles"]) > 0)

    def test_ws_catchup_and_live(self) -> None:
        for t in (100, 160, 220):
            self._ingest(t)

        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 0})

            seen = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            self.assertEqual([m["type"] for m in seen], ["candle_closed", "candle_closed", "candle_closed"])
            self.assertEqual([m["candle"]["candle_time"] for m in seen], [100, 160, 220])

            self._ingest(280)
            live = ws.receive_json()
            self.assertEqual(live["type"], "candle_closed")
            self.assertEqual(live["candle"]["candle_time"], 280)

    def test_ws_gap_is_emitted(self) -> None:
        # Seed with one candle.
        self._ingest(100)

        with self.client.websocket_connect("/ws/market") as ws:
            # Subscribe at candle_time=100 so hub expects next=160 for 1m.
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100})

            # Skip 160 and ingest 220 => should emit gap then candle_closed.
            self._ingest(220)
            gap = ws.receive_json()
            self.assertEqual(gap["type"], "gap")
            self.assertEqual(gap["series_id"], self.series_id)
            self.assertEqual(gap["expected_next_time"], 160)
            self.assertEqual(gap["actual_time"], 220)

            msg = ws.receive_json()
            self.assertEqual(msg["type"], "candle_closed")
            self.assertEqual(msg["candle"]["candle_time"], 220)

    def test_ws_gap_race_does_not_duplicate(self) -> None:
        # Seed with one candle.
        self._ingest(100)

        started = threading.Event()
        proceed = threading.Event()

        from backend.app.storage.candle_store import CandleStore

        original_get_closed = CandleStore.get_closed

        def delayed_get_closed(self, series_id: str, *, since: int | None, limit: int):
            started.set()
            proceed.wait(timeout=1.0)
            return original_get_closed(self, series_id, since=since, limit=limit)

        with mock.patch("backend.app.storage.candle_store.CandleStore.get_closed", new=delayed_get_closed):
            with self.client.websocket_connect("/ws/market") as ws:
                ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100})

                if not started.wait(timeout=1.0):
                    proceed.set()
                    self.fail("catchup did not start")

                self._ingest(220)
                proceed.set()

                gap = ws.receive_json()
                self.assertEqual(gap["type"], "gap")
                self.assertEqual(gap["series_id"], self.series_id)
                self.assertEqual(gap["expected_next_time"], 160)
                self.assertEqual(gap["actual_time"], 220)

                msg = ws.receive_json()
                self.assertEqual(msg["type"], "candle_closed")
                self.assertEqual(msg["candle"]["candle_time"], 220)

                got: dict[str, object] = {}

                def recv_one() -> None:
                    try:
                        got["msg"] = ws.receive_json()
                    except BaseException as e:
                        got["exc"] = e

                t = threading.Thread(target=recv_one, daemon=True)
                t.start()
                t.join(timeout=0.2)
                self.assertTrue(t.is_alive(), "unexpected extra ws message after catchup race")
                ws.close()
                t.join(timeout=1.0)
                self.assertNotIn("msg", got)

    def test_ws_live_gap_backfill_rehydrates_before_live_candle(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL"] = "1"
        self.client.close()
        self.client = TestClient(create_app())
        self._ingest(100)

        def fake_backfill(*, store, series_id, expected_next_time, actual_time, **kwargs):
            self.assertEqual(series_id, self.series_id)
            self.assertEqual(expected_next_time, 160)
            self.assertEqual(actual_time, 220)
            with store.connect() as conn:
                store.upsert_closed_in_conn(
                    conn,
                    self.series_id,
                    CandleClosed(candle_time=160, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                conn.commit()
            return 1

        with mock.patch("backend.app.market.runtime_components.backfill_market_gap_best_effort", side_effect=fake_backfill):
            with self.client.websocket_connect("/ws/market") as ws:
                ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": 100})
                self._ingest(220)

                msg1 = ws.receive_json()
                self.assertEqual(msg1["type"], "candle_closed")
                self.assertEqual(msg1["candle"]["candle_time"], 160)

                msg2 = ws.receive_json()
                self.assertEqual(msg2["type"], "candle_closed")
                self.assertEqual(msg2["candle"]["candle_time"], 220)


if __name__ == "__main__":
    unittest.main()
