from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend.app.ingest_supervisor as ingest_supervisor_mod
from backend.app.main import create_app


class MarketWebSocketDisconnectReleasesOndemandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_ingest_loop = ingest_supervisor_mod.run_whitelist_ingest_loop

        async def _dummy_ingest_loop(*, stop, **_kwargs):  # type: ignore[no-untyped-def]
            await stop.wait()

        ingest_supervisor_mod.run_whitelist_ingest_loop = _dummy_ingest_loop

        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.whitelist_path = Path(self.tmpdir.name) / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")

        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        os.environ["TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"

        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        ingest_supervisor_mod.run_whitelist_ingest_loop = self._orig_ingest_loop
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)

    def _refcount(self) -> int | None:
        res = self.client.get("/api/market/debug/ingest_state")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for job in data.get("jobs", []):
            if job.get("series_id") == self.series_id:
                return int(job.get("refcount"))
        return None

    def test_disconnect_decrements_ondemand_refcount(self) -> None:
        with self.client.websocket_connect("/ws/market") as ws:
            ws.send_json({"type": "subscribe", "series_id": self.series_id, "since": None})
            self.assertEqual(self._refcount(), 1)

        # After websocket disconnect, backend must release the ondemand ingest refcount.
        self.assertEqual(self._refcount(), 0)

