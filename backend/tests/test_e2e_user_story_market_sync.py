from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


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

        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")

        self.client = TestClient(create_app())

        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)

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


if __name__ == "__main__":
    unittest.main()

