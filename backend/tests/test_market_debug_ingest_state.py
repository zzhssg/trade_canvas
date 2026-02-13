from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.data_reconcile_service import (
    ReconcileDiffSnapshot,
    ReconcileSeriesSnapshot,
    ReconcileSideSnapshot,
)
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
        os.environ.pop("TRADE_CANVAS_ENABLE_RUNTIME_METRICS", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_PG_STORE", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DUAL_WRITE", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_DSN", None)
        os.environ.pop("TRADE_CANVAS_POSTGRES_SCHEMA", None)

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

    def test_debug_metrics_404_when_runtime_metrics_disabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = TestClient(create_app())
        resp = client.get("/api/market/debug/metrics")
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_debug_metrics_200_when_enabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_RUNTIME_METRICS"] = "1"
        client = TestClient(create_app())
        ingest = client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": "binance:futures:BTC/USDT:1m",
                "candle": {"candle_time": 1700000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            },
        )
        self.assertEqual(ingest.status_code, 200, ingest.text)

        resp = client.get("/api/market/debug/metrics")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertTrue(payload.get("enabled"))
        self.assertIn("counters", payload)
        self.assertIn("gauges", payload)
        self.assertIn("timers", payload)

    def test_debug_series_health_reports_gap_and_bucket_completeness(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = TestClient(create_app())
        base_series_id = "binance:futures:BTC/USDT:1m"
        derived_series_id = "binance:futures:BTC/USDT:5m"
        for t in (300, 360, 420, 540, 600, 660):
            client.post(
                "/api/market/ingest/candle_closed",
                json={
                    "series_id": base_series_id,
                    "candle": {"candle_time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                },
            )
        client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": derived_series_id,
                "candle": {"candle_time": 300, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            },
        )
        client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": derived_series_id,
                "candle": {"candle_time": 900, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            },
        )

        resp = client.get(
            "/api/market/debug/series_health",
            params={"series_id": derived_series_id, "max_recent_gaps": 3, "recent_base_buckets": 2},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["series_id"], derived_series_id)
        self.assertEqual(payload["gap_count"], 1)
        self.assertEqual(payload["max_gap_seconds"], 600)
        self.assertEqual(payload["base_series_id"], base_series_id)
        self.assertEqual(len(payload["base_bucket_completeness"]), 2)
        self.assertEqual(payload["base_bucket_completeness"][-1]["bucket_open_time"], 600)
        self.assertEqual(payload["base_bucket_completeness"][-1]["expected_minutes"], 5)
        self.assertEqual(payload["base_bucket_completeness"][-1]["actual_minutes"], 2)

    def test_debug_reconcile_404_when_pg_store_disabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = TestClient(create_app())
        resp = client.get(
            "/api/market/debug/reconcile",
            params={"series_id": "binance:futures:BTC/USDT:1m"},
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_debug_reconcile_200_when_debug_and_pg_store_enabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_PG_STORE"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_DUAL_WRITE"] = "1"
        os.environ["TRADE_CANVAS_POSTGRES_DSN"] = "postgresql://tc:tc@127.0.0.1:5432/tc"
        os.environ["TRADE_CANVAS_POSTGRES_SCHEMA"] = "trade_canvas"

        fake_snapshot = ReconcileSeriesSnapshot(
            series_id="binance:futures:BTC/USDT:1m",
            range_start=100,
            range_end=160,
            sqlite=ReconcileSideSnapshot(
                head_time=160,
                first_time=100,
                count=2,
                candle_time_sum=260,
                close_micro_sum=3000000,
            ),
            postgres=ReconcileSideSnapshot(
                head_time=160,
                first_time=100,
                count=2,
                candle_time_sum=260,
                close_micro_sum=3000000,
            ),
            diff=ReconcileDiffSnapshot(
                head_match=True,
                count_match=True,
                checksum_match=True,
                match=True,
            ),
        )

        with patch("backend.app.container._maybe_bootstrap_postgres", return_value=None):
            with patch(
                "backend.app.data_reconcile_service.DataReconcileService.reconcile_series",
                return_value=fake_snapshot,
            ):
                client = TestClient(create_app())
                resp = client.get(
                    "/api/market/debug/reconcile",
                    params={"series_id": "binance:futures:BTC/USDT:1m"},
                )

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["series_id"], "binance:futures:BTC/USDT:1m")
        self.assertTrue(payload["diff"]["match"])


if __name__ == "__main__":
    unittest.main()
