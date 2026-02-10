from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketDebugIngestStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)

    def test_debug_ingest_state_404_when_disabled(self) -> None:
        client = TestClient(create_app())
        resp = client.get("/api/market/debug/ingest_state")
        self.assertEqual(resp.status_code, 404)

    def test_debug_ingest_state_200_when_enabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = TestClient(create_app())
        resp = client.get("/api/market/debug/ingest_state")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertIn("jobs", payload)
        self.assertIsInstance(payload["jobs"], list)

    def test_debug_ingest_state_respects_runtime_env_toggle(self) -> None:
        client = TestClient(create_app())

        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        resp_enabled = client.get("/api/market/debug/ingest_state")
        self.assertEqual(resp_enabled.status_code, 200, resp_enabled.text)

        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "0"
        resp_disabled = client.get("/api/market/debug/ingest_state")
        self.assertEqual(resp_disabled.status_code, 404, resp_disabled.text)


if __name__ == "__main__":
    unittest.main()
