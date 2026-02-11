from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app


class MarketHealthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        os.environ["TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2"] = "1"
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        self.client = TestClient(create_app())

    def _recreate_client(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2", None)
        os.environ.pop("TRADE_CANVAS_KLINE_HEALTH_BACKFILL_RECENT_SECONDS", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)

    @staticmethod
    def _ingest_closed(client: TestClient, series_id: str, candle_time: int) -> None:
        resp = client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": series_id,
                "candle": {
                    "candle_time": int(candle_time),
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 10,
                },
            },
        )
        assert resp.status_code == 200, resp.text

    def test_market_health_404_when_feature_disabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2"] = "0"
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)
        self._recreate_client()
        resp = self.client.get("/api/market/health", params={"series_id": "binance:futures:BTC/USDT:5m"})
        self.assertEqual(resp.status_code, 404)

    def test_market_health_available_when_debug_api_enabled(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2"] = "0"
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        self._recreate_client()
        series_id = "binance:futures:BTC/USDT:5m"
        self._ingest_closed(self.client, series_id, candle_time=300)
        resp = self.client.get("/api/market/health", params={"series_id": series_id, "now_time": 960})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_market_health_red_when_lagging_without_backfill(self) -> None:
        series_id = "binance:futures:BTC/USDT:5m"
        self._ingest_closed(self.client, series_id, candle_time=300)

        resp = self.client.get("/api/market/health", params={"series_id": series_id, "now_time": 960})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "red")
        self.assertEqual(payload["missing_seconds"], 300)
        self.assertEqual(payload["missing_candles"], 1)

    def test_market_health_yellow_when_backfill_recent_and_still_lagging(self) -> None:
        os.environ["TRADE_CANVAS_KLINE_HEALTH_BACKFILL_RECENT_SECONDS"] = "120"
        self._recreate_client()
        series_id = "binance:futures:BTC/USDT:5m"
        self._ingest_closed(self.client, series_id, candle_time=300)
        app = cast(Any, self.client.app)
        tracker = app.state.container.market_runtime.backfill_progress
        tracker.begin(
            series_id=series_id,
            start_missing_seconds=600,
            start_missing_candles=2,
            reason="tail_coverage",
            now_time=910,
        )
        tracker.succeed(
            series_id=series_id,
            current_missing_seconds=300,
            current_missing_candles=1,
            note="tail_coverage_partial",
            now_time=940,
        )

        resp = self.client.get("/api/market/health", params={"series_id": series_id, "now_time": 960})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "yellow")
        self.assertEqual(payload["missing_seconds"], 300)
        self.assertEqual(payload["backfill"]["state"], "succeeded")
        self.assertEqual(int(payload["backfill"]["progress_pct"]), 50)

    def test_market_health_green_when_up_to_date(self) -> None:
        series_id = "binance:futures:BTC/USDT:5m"
        self._ingest_closed(self.client, series_id, candle_time=600)
        resp = self.client.get("/api/market/health", params={"series_id": series_id, "now_time": 960})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "green")
        self.assertEqual(payload["missing_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
