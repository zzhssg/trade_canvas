from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _post_candle(client: TestClient, *, series_id: str, candle_time: int, price: float) -> None:
    res = client.post(
        "/api/market/ingest/candle_closed",
        json={
            "series_id": series_id,
            "candle": {
                "candle_time": int(candle_time),
                "open": float(price),
                "high": float(price),
                "low": float(price),
                "close": float(price),
                "volume": 10,
            },
        },
    )
    assert res.status_code == 200, res.text


class PlotPivotIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_PLOT_INGEST"] = "1"
        # Small windows so tests stay tiny & deterministic.
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_PLOT_LOOKBACK_CANDLES"] = "200"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_PLOT_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_PLOT_LOOKBACK_CANDLES",
        ):
            os.environ.pop(k, None)

    def test_major_pivot_is_delayed_and_idempotent(self) -> None:
        # Pattern: 1,2,5,2,1 creates a clear local max at the center (t=180).
        base = 60
        prices = [1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            _post_candle(self.client, series_id=self.series_id, candle_time=t, price=p)

        res = self.client.get("/api/plot/delta", params={"series_id": self.series_id})
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        events = payload.get("overlay_events") or []

        # Major window=2: pivot at idx=2 visible at idx=4 -> visible_time=times[4].
        # pivot_time=times[2].
        major = [e for e in events if e.get("kind") == "pivot.major"]
        self.assertTrue(major, "expected at least one pivot.major event")
        # Find the resistance at pivot_time == times[2]
        hit = None
        for e in major:
            pl = e.get("payload") or {}
            if pl.get("pivot_time") == times[2] and pl.get("direction") == "resistance":
                hit = e
                break
        self.assertIsNotNone(hit, "missing expected resistance pivot.major event")
        self.assertEqual(int(hit["candle_time"]), times[4])
        self.assertEqual(int(hit["payload"]["visible_time"]), times[4])

        # Idempotent: re-ingest the same candles should not create duplicate events.
        for t, p in zip(times, prices, strict=True):
            _post_candle(self.client, series_id=self.series_id, candle_time=t, price=p)
        res2 = self.client.get("/api/plot/delta", params={"series_id": self.series_id})
        self.assertEqual(res2.status_code, 200, res2.text)
        events2 = (res2.json().get("overlay_events") or [])
        # Unique by (series_id, kind, pivot_time, direction) -> count should be unchanged for that key.
        def _keys(evts: list[dict]) -> set[tuple]:
            out = set()
            for e in evts:
                pl = e.get("payload") or {}
                out.add((e.get("kind"), pl.get("pivot_time"), pl.get("direction")))
            return out

        self.assertEqual(_keys(events2), _keys(events))

    def test_seed_equals_incremental_event_set(self) -> None:
        # Use a longer sequence that yields at least one major and several minors.
        base = 60
        prices = [1, 2, 3, 5, 3, 2, 1, 2, 3, 1, 0.5, 1, 2]
        times = [base * (i + 1) for i in range(len(prices))]

        # Run A: incremental
        for t, p in zip(times, prices, strict=True):
            _post_candle(self.client, series_id=self.series_id, candle_time=t, price=p)
        res_a = self.client.get("/api/plot/delta", params={"series_id": self.series_id})
        self.assertEqual(res_a.status_code, 200, res_a.text)
        events_a = res_a.json().get("overlay_events") or []
        keys_a = {
            (e.get("kind"), (e.get("payload") or {}).get("pivot_time"), (e.get("payload") or {}).get("direction"))
            for e in events_a
        }

        # Run B: seed (new DB), ingest same candles (still incremental at the endpoint level, but should be deterministic).
        self.tearDown()
        self.setUp()
        for t, p in zip(times, prices, strict=True):
            _post_candle(self.client, series_id=self.series_id, candle_time=t, price=p)
        res_b = self.client.get("/api/plot/delta", params={"series_id": self.series_id})
        self.assertEqual(res_b.status_code, 200, res_b.text)
        events_b = res_b.json().get("overlay_events") or []
        keys_b = {
            (e.get("kind"), (e.get("payload") or {}).get("pivot_time"), (e.get("payload") or {}).get("direction"))
            for e in events_b
        }

        self.assertEqual(keys_a, keys_b)


if __name__ == "__main__":
    unittest.main()

