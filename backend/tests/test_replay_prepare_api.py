from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.core.schemas import CandleClosed


class ReplayPrepareApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.db_path = root / "market.db"
        self.whitelist_path = root / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")

        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "0"

        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

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
            "TRADE_CANVAS_ENABLE_DEBUG_API",
        ):
            os.environ.pop(key, None)

    def _seed_closed(self, *, candle_time: int, price: float) -> None:
        app = cast(Any, self.client.app)
        app.state.container.store.upsert_closed(
            self.series_id,
            CandleClosed(
                candle_time=int(candle_time),
                open=float(price),
                high=float(price),
                low=float(price),
                close=float(price),
                volume=1.0,
            ),
        )

    def test_prepare_replay_pipeline_path_works(self) -> None:
        self._seed_closed(candle_time=1_700_000_000, price=100.0)

        res = self.client.post(
            "/api/replay/prepare",
            json={
                "series_id": self.series_id,
                "to_time": 1_700_000_000,
                "window_candles": 2000,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(int(payload["aligned_time"]), 1_700_000_000)
        self.assertEqual(payload["series_id"], self.series_id)

    def test_prepare_replay_pipeline_path_refreshes_ledger(self) -> None:
        self._seed_closed(candle_time=1_700_000_060, price=101.0)

        res = self.client.post(
            "/api/replay/prepare",
            json={
                "series_id": self.series_id,
                "to_time": 1_700_000_060,
                "window_candles": 2000,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(int(payload["aligned_time"]), 1_700_000_060)
        self.assertGreaterEqual(int(payload["factor_head_time"]), 1_700_000_060)
        self.assertGreaterEqual(int(payload["overlay_head_time"]), 1_700_000_060)


if __name__ == "__main__":
    unittest.main()
