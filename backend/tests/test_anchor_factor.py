from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


class AnchorFactorTests(unittest.TestCase):
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

    def test_anchor_has_stable_switches_and_head_refs(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 9, 2, 1, 2, 8, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()

        self.assertIn("anchor", payload["factors"])
        a = payload["snapshots"]["anchor"]
        head = a.get("head") or {}
        cur = head.get("current_anchor_ref")
        self.assertIsInstance(cur, dict)
        self.assertIn(cur.get("kind"), ("confirmed", "candidate"))
        self.assertLessEqual(int(cur.get("end_time") or 0), int(payload["at_time"]))

        hist = a.get("history") or {}
        anchors = hist.get("anchors") or []
        switches = hist.get("switches") or []
        self.assertGreaterEqual(len(switches), 1, "expected at least one stable anchor switch event")
        self.assertEqual(len(anchors), len(switches), "history anchors should align 1:1 with switches")
        for idx, sw in enumerate(switches):
            new_anchor = sw.get("new_anchor") if isinstance(sw, dict) else None
            self.assertIsInstance(new_anchor, dict)
            self.assertEqual(anchors[idx], new_anchor)

        # Idempotent: re-ingesting the last candle should not grow switches (FactorStore UNIQUE event_key).
        before = len(switches)
        self._ingest(times[-1], float(prices[-1]))
        res2 = self.client.get("/api/factor/slices", params={"series_id": self.series_id, "at_time": times[-1]})
        self.assertEqual(res2.status_code, 200, res2.text)
        payload2 = res2.json()
        switches2 = (payload2["snapshots"]["anchor"].get("history") or {}).get("switches") or []
        self.assertEqual(len(switches2), before)


if __name__ == "__main__":
    unittest.main()
