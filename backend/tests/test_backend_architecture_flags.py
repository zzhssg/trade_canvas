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
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_ENABLE_READ_STRICT_MODE",
            "TRADE_CANVAS_ENABLE_READ_IMPLICIT_RECOMPUTE",
            "TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH",
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
            pipeline = container.ingest_pipeline
            self.assertIs(runtime.ingest_pipeline, pipeline)
            self.assertIs(runtime.flags, container.flags)
            self.assertIs(runtime.runtime_flags, container.runtime_flags)
            self.assertIs(container.hub, runtime.hub)
            self.assertIs(getattr(pipeline, "_hub", None), container.hub)
        finally:
            client.close()

    def test_read_strict_mode_blocks_implicit_factor_recompute(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "0"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_READ_STRICT_MODE"] = "1"

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

    def test_read_implicit_recompute_flag_is_wired_to_factor_read_service(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(container.runtime_flags.enable_read_implicit_recompute)
            self.assertFalse(container.factor_read_service.implicit_recompute_enabled)
        finally:
            client.close()

    def test_ingest_ws_pipeline_publish_flag_is_wired_to_supervisor(self) -> None:
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertFalse(container.runtime_flags.enable_ingest_ws_pipeline_publish)
            self.assertFalse(container.supervisor.ws_pipeline_publish_enabled)
        finally:
            client.close()

        os.environ["TRADE_CANVAS_ENABLE_INGEST_WS_PIPELINE_PUBLISH"] = "1"
        client = self._build_client()
        try:
            app = cast(Any, client.app)
            container = app.state.container
            self.assertTrue(container.runtime_flags.enable_ingest_ws_pipeline_publish)
            self.assertTrue(container.supervisor.ws_pipeline_publish_enabled)
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
            self.assertIsNotNone(getattr(container.supervisor, "_reaper_task", None))


if __name__ == "__main__":
    unittest.main()
