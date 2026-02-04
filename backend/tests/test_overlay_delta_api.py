from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class OverlayDeltaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_PLOT_INGEST"] = "0"  # overlay v0 reads FactorStore, not PlotStore
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_PLOT_INGEST",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
        ):
            os.environ.pop(k, None)

    def _ingest(self, t: int, price: float) -> None:
        res = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": t, "open": price, "high": price, "low": price, "close": price, "volume": 1},
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_overlay_delta_has_markers_and_is_cursor_idempotent(self) -> None:
        # A short wave producing alternating pivots with window_major=2 (deterministic).
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/overlay/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertEqual(payload["to_candle_time"], times[-1])
        self.assertGreaterEqual(len(payload["instruction_catalog_patch"]), 1)
        self.assertTrue(any(i.startswith("pivot.major:") or i.startswith("pivot.minor:") for i in payload["active_ids"]))

        # Regression: pivot.major marker keeps `text` field but should be blank (no legacy "P").
        majors: list[dict] = []
        for item in payload["instruction_catalog_patch"]:
            if not isinstance(item, dict) or item.get("kind") != "marker":
                continue
            d = item.get("definition")
            if not isinstance(d, dict):
                continue
            if d.get("feature") == "pivot.major":
                majors.append(d)
        self.assertTrue(majors, "expected at least one pivot.major marker in patch")
        self.assertIn("text", majors[0])
        self.assertEqual(majors[0].get("text"), "")

        next_version = int(payload["next_cursor"]["version_id"])
        self.assertGreater(next_version, 0)

        # Cursor idempotency: after consuming to latest cursor, patch should be empty.
        res2 = self.client.get("/api/overlay/delta", params={"series_id": self.series_id, "cursor_version_id": next_version})
        self.assertEqual(res2.status_code, 200, res2.text)
        payload2 = res2.json()
        self.assertEqual(int(payload2["next_cursor"]["version_id"]), next_version)
        self.assertEqual(payload2["instruction_catalog_patch"], [])

        # Re-ingest the same last candle: no new versions should appear.
        self._ingest(times[-1], float(prices[-1]))
        res3 = self.client.get("/api/overlay/delta", params={"series_id": self.series_id, "cursor_version_id": next_version})
        self.assertEqual(res3.status_code, 200, res3.text)
        payload3 = res3.json()
        self.assertEqual(int(payload3["next_cursor"]["version_id"]), next_version)
        self.assertEqual(payload3["instruction_catalog_patch"], [])


if __name__ == "__main__":
    unittest.main()
