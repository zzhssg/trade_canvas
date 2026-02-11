from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app


class ReadRepairApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.whitelist_path = Path(self.tmpdir.name) / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        os.environ["TRADE_CANVAS_ENABLE_READ_REPAIR_API"] = "1"
        self.series_id = "binance:futures:BTC/USDT:1m"
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_ENABLE_READ_REPAIR_API",
        ):
            os.environ.pop(key, None)

    def _recreate_client(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.client = TestClient(create_app())

    def _ingest(self, candle_time: int, price: float) -> None:
        res = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {
                    "candle_time": int(candle_time),
                    "open": float(price),
                    "high": float(price),
                    "low": float(price),
                    "close": float(price),
                    "volume": 1.0,
                },
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def _overlay_store(self):
        app = cast(Any, self.client.app)
        return app.state.container.overlay_store

    def test_repair_overlay_endpoint_disabled_by_default(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_READ_REPAIR_API"] = "0"
        self._recreate_client()
        res = self.client.post(
            "/api/dev/repair/overlay",
            json={"series_id": self.series_id},
        )
        self.assertEqual(res.status_code, 404, res.text)

    def test_repair_overlay_endpoint_recovers_tampered_overlay(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (idx + 1) for idx in range(len(prices))]
        for candle_time, price in zip(times, prices, strict=True):
            self._ingest(candle_time, float(price))

        first = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn("anchor.current", first.json().get("active_ids") or [])

        overlay_store = self._overlay_store()
        with overlay_store.connect() as conn:
            conn.execute(
                "DELETE FROM overlay_instruction_versions WHERE series_id = ? AND instruction_id = ?",
                (self.series_id, "anchor.current"),
            )
            conn.commit()

        out_of_sync = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(out_of_sync.status_code, 409, out_of_sync.text)
        self.assertIn("ledger_out_of_sync:overlay", out_of_sync.text)

        repair = self.client.post(
            "/api/dev/repair/overlay",
            json={"series_id": self.series_id, "to_time": int(times[-1])},
        )
        self.assertEqual(repair.status_code, 200, repair.text)
        payload = repair.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("overlay.reset_series", payload.get("steps") or [])
        self.assertIn("overlay.ingest_closed", payload.get("steps") or [])

        repaired = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(repaired.status_code, 200, repaired.text)
        self.assertIn("anchor.current", repaired.json().get("active_ids") or [])


if __name__ == "__main__":
    unittest.main()
