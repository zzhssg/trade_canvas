from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class WorldStateFrameApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        os.environ["TRADE_CANVAS_OVERLAY_WINDOW_CANDLES"] = "2000"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def _recreate_client(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
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

    def test_frame_at_time_is_aligned_and_candle_id_matches_components(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        t = 777  # should floor to 720 for 1m
        res = self.client.get("/api/frame/at_time", params={"series_id": self.series_id, "at_time": t, "window_candles": 2000})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["series_id"], self.series_id)
        self.assertEqual(int(payload["time"]["at_time"]), t)
        self.assertEqual(int(payload["time"]["aligned_time"]), 720)
        self.assertEqual(payload["time"]["candle_id"], f"{self.series_id}:720")

        fs = payload["factor_slices"]
        self.assertEqual(fs["candle_id"], f"{self.series_id}:720")
        ds = payload["draw_state"]
        self.assertEqual(ds["to_candle_id"], f"{self.series_id}:720")
        self.assertEqual(int(ds["to_candle_time"]), 720)

    def test_frame_live_returns_404_when_empty(self) -> None:
        res = self.client.get("/api/frame/live", params={"series_id": self.series_id, "window_candles": 2000})
        self.assertEqual(res.status_code, 404, res.text)
        self.assertIn("no_data", res.text)

    def test_frame_at_time_returns_404_when_empty(self) -> None:
        res = self.client.get("/api/frame/at_time", params={"series_id": self.series_id, "at_time": 60, "window_candles": 2000})
        self.assertEqual(res.status_code, 404, res.text)
        self.assertIn("no_data", res.text)

    def test_frame_at_time_returns_409_when_overlay_not_ready(self) -> None:
        # Disable overlay ingest so draw/delta cannot be aligned for point queries.
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "0"
        self._recreate_client()
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/frame/at_time", params={"series_id": self.series_id, "at_time": times[-1], "window_candles": 2000})
        self.assertEqual(res.status_code, 409, res.text)
        self.assertIn("ledger_out_of_sync:overlay", res.text)

    def test_frame_live_returns_latest(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/frame/live", params={"series_id": self.series_id, "window_candles": 2000})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(int(payload["time"]["aligned_time"]), times[-1])
        self.assertEqual(payload["time"]["candle_id"], f"{self.series_id}:{times[-1]}")
        self.assertEqual(payload["factor_slices"]["candle_id"], f"{self.series_id}:{times[-1]}")
        self.assertEqual(payload["draw_state"]["to_candle_id"], f"{self.series_id}:{times[-1]}")

    def test_frame_at_time_debug_mode_no_name_error(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        try:
            self._recreate_client()
            base = 60
            prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
            times = [base * (i + 1) for i in range(len(prices))]
            for t, p in zip(times, prices, strict=True):
                self._ingest(t, float(p))

            res = self.client.get("/api/frame/at_time", params={"series_id": self.series_id, "at_time": 301, "window_candles": 2000})
            self.assertEqual(res.status_code, 200, res.text)
            payload = res.json()
            self.assertEqual(int(payload["time"]["aligned_time"]), 300)
        finally:
            os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)


if __name__ == "__main__":
    unittest.main()
