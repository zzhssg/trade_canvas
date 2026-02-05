from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class DrawDeltaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_PLOT_INGEST"] = "0"
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

    def test_draw_delta_is_overlay_compatible_and_cursor_idempotent(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_overlay = self.client.get("/api/overlay/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_overlay.status_code, 200, res_overlay.text)
        overlay = res_overlay.json()

        res_draw = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_draw.status_code, 200, res_draw.text)
        draw = res_draw.json()

        self.assertEqual(draw["series_id"], self.series_id)
        self.assertEqual(draw["to_candle_time"], times[-1])
        self.assertIn("series_points", draw)
        self.assertEqual(draw["series_points"], {})

        self.assertEqual(draw["active_ids"], overlay["active_ids"])
        self.assertEqual(draw["instruction_catalog_patch"], overlay["instruction_catalog_patch"])
        self.assertEqual(int(draw["next_cursor"]["version_id"]), int(overlay["next_cursor"]["version_id"]))

        def pick_marker_defs(feature: str) -> list[dict]:
            out: list[dict] = []
            for item in overlay.get("instruction_catalog_patch") or []:
                if not isinstance(item, dict) or item.get("kind") != "marker":
                    continue
                d = item.get("definition")
                if not isinstance(d, dict):
                    continue
                if d.get("feature") == feature:
                    out.append(d)
            return out

        majors = pick_marker_defs("pivot.major")
        minors = pick_marker_defs("pivot.minor")
        self.assertTrue(majors, "expected at least one pivot.major marker in patch")
        self.assertTrue(minors, "expected at least one pivot.minor marker in patch")
        self.assertEqual(str(majors[0].get("shape")), "circle")
        self.assertEqual(str(minors[0].get("shape")), "circle")
        self.assertAlmostEqual(float(majors[0].get("size")), 1.0, places=6)
        self.assertAlmostEqual(float(minors[0].get("size")), 0.5, places=6)

        next_version = int(draw["next_cursor"]["version_id"])
        self.assertGreater(next_version, 0)

        res2 = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": next_version},
        )
        self.assertEqual(res2.status_code, 200, res2.text)
        payload2 = res2.json()
        self.assertEqual(int(payload2["next_cursor"]["version_id"]), next_version)
        self.assertEqual(payload2["instruction_catalog_patch"], [])
        self.assertEqual(payload2["series_points"], {})

    def test_draw_delta_supports_at_time_and_fails_when_overlay_lags(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # at_time clamps the upper-bound to an aligned closed candle_time.
        t_mid = times[4]
        res_mid = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": 0, "at_time": t_mid},
        )
        self.assertEqual(res_mid.status_code, 200, res_mid.text)
        payload_mid = res_mid.json()
        self.assertEqual(payload_mid["to_candle_time"], t_mid)
        self.assertEqual(payload_mid["to_candle_id"], f"{self.series_id}:{t_mid}")

        # Force overlay head_time to lag behind, then requesting a later at_time must fail-safe.
        overlay_store = self.client.app.state.overlay_store
        with overlay_store.connect() as conn:
            overlay_store.upsert_head_time_in_conn(conn, series_id=self.series_id, head_time=t_mid)
            conn.commit()

        res_late = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": 0, "at_time": times[-1]},
        )
        self.assertEqual(res_late.status_code, 409, res_late.text)
        self.assertIn("ledger_out_of_sync", res_late.text)


if __name__ == "__main__":
    unittest.main()
