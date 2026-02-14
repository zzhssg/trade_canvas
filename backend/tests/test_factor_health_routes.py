from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.core.schemas import CandleClosed
from backend.app.main import create_app


class FactorHealthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "factor-health.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)

    @staticmethod
    def _series_id() -> str:
        return "binance:futures:BTC/USDT:5m"

    @staticmethod
    def _ingest_closed(client: TestClient, *, series_id: str, candle_time: int) -> None:
        resp = client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": series_id,
                "candle": {
                    "candle_time": int(candle_time),
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.8,
                    "close": 1.3,
                    "volume": 10.0,
                },
            },
        )
        assert resp.status_code == 200, resp.text

    @staticmethod
    def _upsert_store_only(client: TestClient, *, series_id: str, candle_time: int) -> None:
        app = cast(Any, client.app)
        store = app.state.container.store
        candle = CandleClosed(
            candle_time=int(candle_time),
            open=1.0,
            high=2.0,
            low=0.8,
            close=1.3,
            volume=10.0,
        )
        with store.connect() as conn:
            store.upsert_closed_in_conn(conn, series_id, candle)
            conn.commit()

    def test_factor_health_gray_when_store_head_missing(self) -> None:
        series_id = self._series_id()
        resp = self.client.get("/api/factor/health", params={"series_id": series_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "gray")
        self.assertEqual(payload["status_reason"], "no_store_head")
        self.assertIsNone(payload["store_head_time"])

    def test_factor_health_green_when_heads_aligned(self) -> None:
        series_id = self._series_id()
        self._ingest_closed(self.client, series_id=series_id, candle_time=300)
        resp = self.client.get("/api/factor/health", params={"series_id": series_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "green")
        self.assertEqual(payload["status_reason"], "up_to_date")
        self.assertEqual(payload["factor_delay_seconds"], 0)
        self.assertEqual(payload["overlay_delay_seconds"], 0)

    def test_factor_health_yellow_when_lagging_one_candle(self) -> None:
        series_id = self._series_id()
        self._ingest_closed(self.client, series_id=series_id, candle_time=300)
        self._upsert_store_only(self.client, series_id=series_id, candle_time=600)
        resp = self.client.get("/api/factor/health", params={"series_id": series_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "yellow")
        self.assertEqual(payload["status_reason"], "lagging_one_candle")
        self.assertEqual(payload["factor_delay_seconds"], 300)
        self.assertEqual(payload["overlay_delay_seconds"], 300)
        self.assertEqual(payload["max_delay_candles"], 1)

    def test_factor_health_red_when_lagging_many_candles(self) -> None:
        series_id = self._series_id()
        self._ingest_closed(self.client, series_id=series_id, candle_time=300)
        self._upsert_store_only(self.client, series_id=series_id, candle_time=1500)
        resp = self.client.get("/api/factor/health", params={"series_id": series_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "red")
        self.assertEqual(payload["status_reason"], "lagging_many_candles")
        self.assertGreaterEqual(payload["max_delay_candles"], 2)

    def test_factor_health_red_when_factor_and_overlay_missing(self) -> None:
        series_id = self._series_id()
        self._upsert_store_only(self.client, series_id=series_id, candle_time=300)
        resp = self.client.get("/api/factor/health", params={"series_id": series_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "red")
        self.assertEqual(payload["status_reason"], "missing_factor_overlay_head")
        self.assertIsNone(payload["factor_head_time"])
        self.assertIsNone(payload["overlay_head_time"])

    def test_factor_health_returns_400_for_invalid_series_id(self) -> None:
        resp = self.client.get("/api/factor/health", params={"series_id": "bad"})
        self.assertEqual(resp.status_code, 400, resp.text)


if __name__ == "__main__":
    unittest.main()
