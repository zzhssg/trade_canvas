from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class AnchorSwitchIncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
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

    def test_anchor_switch_reasons_present(self) -> None:
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
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": 1260})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertIn("anchor", payload["factors"])
        anchor = payload["snapshots"]["anchor"]
        anchors = (anchor.get("history") or {}).get("anchors") or []
        switches = anchor["history"]["switches"]
        self.assertEqual(len(anchors), len(switches))
        reasons = {s.get("reason") for s in switches}
        self.assertIn("strong_pen", reasons)
        cur = anchor["head"]["current_anchor_ref"]
        self.assertIsNotNone(cur)
        self.assertLessEqual(int(cur.get("end_time") or 0), int(payload["at_time"]))

    def test_strong_pen_switch_keeps_single_best_ref_per_visible_time(self) -> None:
        base = 60
        prices = [
            100,
            95,
            94,
            92,
            90,
            87,
            88,
            83,
            80,
            77,
            72,
            77,
            72,
            73,
            72,
            73,
            70,
            68,
            70,
            71,
            68,
            66,
            64,
            65,
            63,
            64,
            65,
            70,
            72,
            77,
            82,
            79,
            74,
            75,
            78,
            80,
            83,
            82,
            83,
            80,
            81,
            80,
            83,
            78,
            77,
            72,
            75,
            73,
            68,
            66,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        switches = ((payload.get("snapshots", {}).get("anchor", {}).get("history", {}) or {}).get("switches")) or []

        strong_by_time: dict[int, list[dict]] = {}
        for sw in switches:
            if not isinstance(sw, dict):
                continue
            if str(sw.get("reason") or "") != "strong_pen":
                continue
            st = int(sw.get("switch_time") or 0)
            strong_by_time.setdefault(st, []).append(sw)

        duplicated = {st: items for st, items in strong_by_time.items() if len(items) > 1}
        self.assertEqual(duplicated, {}, "strong_pen switches must be unique per visible_time")

        picked = strong_by_time.get(1620) or []
        self.assertEqual(len(picked), 1)
        ref = picked[0].get("new_anchor") if isinstance(picked[0], dict) else None
        self.assertIsInstance(ref, dict)
        self.assertEqual(int(ref.get("start_time") or 0), 1200)
        self.assertEqual(str(ref.get("kind") or ""), "candidate")


if __name__ == "__main__":
    unittest.main()
