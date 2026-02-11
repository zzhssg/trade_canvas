from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app


class BackendArchitectureFlagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.db_path = root / "market.db"
        self.whitelist_path = root / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for name in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_ENABLE_DEBUG_API",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_ENABLE_READ_LEDGER_WARMUP",
            "TRADE_CANVAS_ENABLE_DEV_API",
            "TRADE_CANVAS_ENABLE_RUNTIME_METRICS",
            "TRADE_CANVAS_ENABLE_MARKET_BACKFILL_PROGRESS_PERSISTENCE",
            "TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE",
            "TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL",
            "TRADE_CANVAS_ENABLE_WHITELIST_INGEST",
            "TRADE_CANVAS_ENABLE_ONDEMAND_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
        ):
            os.environ.pop(name, None)

    def _build_client(self) -> TestClient:
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        return TestClient(create_app())

    def _post_candle(self, client: TestClient, t: int, price: float) -> None:
        res = client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {
                    "candle_time": int(t),
                    "open": float(price),
                    "high": float(price),
                    "low": float(price),
                    "close": float(price),
                    "volume": 1.0,
                },
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_ingest_pipeline_http_path_keeps_main_flow_available(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        os.environ["TRADE_CANVAS_OVERLAY_WINDOW_CANDLES"] = "2000"

        client = self._build_client()
        try:
            for t, p in ((100, 1.0), (160, 2.0), (220, 3.0)):
                self._post_candle(client, t, p)

            candles = client.get(
                "/api/market/candles",
                params={"series_id": self.series_id, "since": 100, "limit": 10},
            )
            self.assertEqual(candles.status_code, 200, candles.text)
            self.assertEqual([c["candle_time"] for c in candles.json()["candles"]], [160, 220])

            factor = client.get(
                "/api/factor/slices",
                params={"series_id": self.series_id, "at_time": 220, "window_candles": 2000},
            )
            self.assertEqual(factor.status_code, 200, factor.text)
            self.assertEqual(factor.json()["candle_id"], f"{self.series_id}:220")
        finally:
            client.close()

    def test_runtime_pipeline_and_hub_use_single_instance(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            runtime = container.market_runtime
            pipeline = runtime.ingest_ctx.ingest_pipeline
            self.assertIs(runtime.ingest_ctx.ingest_pipeline, pipeline)
            self.assertIs(runtime.flags, container.flags)
            self.assertIs(runtime.runtime_flags, container.runtime_flags)
            self.assertIs(getattr(pipeline, "_hub", None), runtime.hub)
            self.assertIs(container.lifecycle.market_runtime, runtime)
            self.assertFalse(hasattr(container.lifecycle, "supervisor"))
        finally:
            client.close()

    def test_read_path_requires_strict_fresh_ledger(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "0"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"

        client = self._build_client()
        try:
            self._post_candle(client, 100, 1.0)

            factor = client.get(
                "/api/factor/slices",
                params={"series_id": self.series_id, "at_time": 100, "window_candles": 2000},
            )
            self.assertEqual(factor.status_code, 409, factor.text)
            self.assertIn("ledger_out_of_sync:factor", factor.text)
        finally:
            client.close()

    def test_factor_read_service_is_strict_by_default(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertTrue(container.factor_read_service.strict_mode)
            self.assertFalse(container.runtime_flags.enable_read_ledger_warmup)
            query_service = container.market_runtime.read_ctx.query
            self.assertFalse(query_service.runtime_flags.enable_read_ledger_warmup)
        finally:
            client.close()

    def test_ledger_warmup_dependency_belongs_to_route_orchestrator_not_query_service(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            query_service = container.market_runtime.read_ctx.query
            warmup_service = container.market_runtime.read_ctx.ledger_warmup
            self.assertFalse(hasattr(query_service, "ingest_pipeline"))
            self.assertTrue(hasattr(warmup_service, "ingest_pipeline"))
        finally:
            client.close()

    def test_db_schema_migrations_are_always_enabled_in_stores(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(hasattr(container.runtime_flags, "enable_db_schema_migrations"))
            self.assertFalse(hasattr(container.store, "schema_migrations_enabled"))
            self.assertFalse(hasattr(container.factor_store, "schema_migrations_enabled"))
            self.assertFalse(hasattr(container.overlay_store, "schema_migrations_enabled"))
        finally:
            client.close()

    def test_dev_api_flag_guards_dev_routes(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(container.runtime_flags.enable_dev_api)
            blocked = client.get("/api/dev/worktrees")
            self.assertEqual(blocked.status_code, 404, blocked.text)
        finally:
            client.close()

        os.environ["TRADE_CANVAS_ENABLE_DEV_API"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertTrue(container.runtime_flags.enable_dev_api)
            allowed = client.get("/api/dev/worktrees")
            self.assertEqual(allowed.status_code, 200, allowed.text)
        finally:
            client.close()

    def test_runtime_metrics_flag_wires_container_and_debug_endpoint(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(container.runtime_flags.enable_runtime_metrics)
            self.assertFalse(container.runtime_metrics.enabled())
            self.assertIs(container.market_runtime.realtime_ctx.ws_subscriptions._runtime_metrics, container.runtime_metrics)
            blocked = client.get("/api/market/debug/metrics")
            self.assertEqual(blocked.status_code, 404, blocked.text)
        finally:
            client.close()

        os.environ["TRADE_CANVAS_ENABLE_RUNTIME_METRICS"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertTrue(container.runtime_flags.enable_runtime_metrics)
            self.assertTrue(container.runtime_metrics.enabled())
            self.assertIs(container.market_runtime.realtime_ctx.ws_subscriptions._runtime_metrics, container.runtime_metrics)
            allowed = client.get("/api/market/debug/metrics")
            self.assertEqual(allowed.status_code, 200, allowed.text)
        finally:
            client.close()

    def test_backfill_progress_persistence_flag_is_wired_to_tracker(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            tracker = container.market_runtime.read_ctx.backfill_progress
            self.assertFalse(container.runtime_flags.enable_market_backfill_progress_persistence)
            self.assertIsNone(getattr(tracker, "_state_path", None))
        finally:
            client.close()

        os.environ["TRADE_CANVAS_ENABLE_MARKET_BACKFILL_PROGRESS_PERSISTENCE"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            tracker = container.market_runtime.read_ctx.backfill_progress
            self.assertTrue(container.runtime_flags.enable_market_backfill_progress_persistence)
            expected_path = self.db_path.parent / "runtime_state" / "market_backfill_progress.json"
            self.assertEqual(Path(getattr(tracker, "_state_path")), expected_path)
        finally:
            client.close()

    def test_ingest_supervisor_uses_single_publish_path(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            snapshot = container.market_runtime.ingest_ctx.supervisor.debug_snapshot
            self.assertTrue(callable(snapshot))
            self.assertFalse(hasattr(container.runtime_flags, "enable_ingest_ws_pipeline_publish"))
        finally:
            client.close()

    def test_ledger_sync_service_flag_wires_single_instance(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(container.runtime_flags.enable_ledger_sync_service)
            self.assertIs(container.read_repair_service.ledger_sync_service, container.ledger_sync_service)
            self.assertIs(container.replay_prepare_service.ledger_sync_service, container.ledger_sync_service)
        finally:
            client.close()

        os.environ["TRADE_CANVAS_ENABLE_LEDGER_SYNC_SERVICE"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertTrue(container.runtime_flags.enable_ledger_sync_service)
            self.assertTrue(container.read_repair_service.enable_ledger_sync_service)
            self.assertTrue(container.replay_prepare_service.enable_ledger_sync_service)
        finally:
            client.close()

    def test_whitelist_mode_starts_reaper_even_without_ondemand(self) -> None:
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        os.environ["TRADE_CANVAS_ENABLE_WHITELIST_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"] = "0"

        with TestClient(create_app()) as client:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertIsNotNone(getattr(container.market_runtime.ingest_ctx.supervisor, "_reaper_task", None))


if __name__ == "__main__":
    unittest.main()
