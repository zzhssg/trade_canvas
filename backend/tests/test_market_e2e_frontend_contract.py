from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class MarketFrontendContractE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"] = "0"
        os.environ["TRADE_CANVAS_ENABLE_WHITELIST_INGEST"] = "0"

        self.series_id = "binance:futures:SOL/USDT:1m"
        self.store = CandleStore(db_path=self.db_path)

        with self.store.connect() as conn:
            candles = [
                CandleClosed(candle_time=60 * i, open=1, high=2, low=0.5, close=1.5, volume=10)
                for i in range(1, 2101)
            ]
            self.store.upsert_many_closed_in_conn(conn, self.series_id, candles)
            conn.commit()

        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_ONDEMAND_INGEST",
            "TRADE_CANVAS_ENABLE_WHITELIST_INGEST",
        ):
            os.environ.pop(k, None)

    def test_frontend_tail_2000_then_ws_new_candle(self) -> None:
        # Frontend initial load: tail (latest 2000) in ascending order.
        resp = self.client.get("/api/market/candles", params={"series_id": self.series_id, "limit": 2000})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertEqual(len(payload["candles"]), 2000)
        times = [c["candle_time"] for c in payload["candles"]]
        self.assertEqual(times, sorted(times))
        self.assertEqual(times[0], 60 * 101)  # 2100 - 2000 + 1
        self.assertEqual(times[-1], 60 * 2100)

        # DB persistence check.
        with self.store.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM candles WHERE series_id = ?", (self.series_id,)).fetchone()
            self.assertEqual(int(row["n"]), 2100)

        last_time = times[-1]
        next_time = last_time + 60

        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": last_time})

            # No immediate catchup expected (since is at head), so push a new closed candle.
            ingest = self.client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": self.series_id,
                    "candle": {
                        "candle_time": next_time,
                        "open": 1,
                        "high": 2,
                        "low": 0.5,
                        "close": 1.5,
                        "volume": 10,
                    },
                },
            )
            self.assertEqual(ingest.status_code, 200)

            msg = ws.receive_json()
            self.assertEqual(msg["type"], "candle_closed")
            self.assertEqual(msg["series_id"], self.series_id)
            self.assertEqual(msg["candle"]["candle_time"], next_time)

        # HTTP incremental should also see the new candle.
        resp2 = self.client.get(
            "/api/market/candles",
            params={"series_id": self.series_id, "since": last_time, "limit": 10},
        )
        self.assertEqual(resp2.status_code, 200)
        payload2 = resp2.json()
        self.assertEqual([c["candle_time"] for c in payload2["candles"]], [next_time])


if __name__ == "__main__":
    unittest.main()

