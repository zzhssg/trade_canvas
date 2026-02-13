from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.overlay.store import OverlayStore
from backend.app.storage.candle_store import CandleStore
from backend.app.core.schemas import CandleClosed


class ReplayOverlayPackageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.db_path = root / "market.db"
        self.artifacts_dir = root / "artifacts"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_REPLAY_PACKAGE"] = "1"
        os.environ["TRADE_CANVAS_ARTIFACTS_DIR"] = str(self.artifacts_dir)
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

        store = CandleStore(db_path=self.db_path)
        overlay_store = OverlayStore(db_path=self.db_path)
        candles = []
        base = 60
        for i in range(40):
            t = base * (i + 1)
            price = float(1 + (i % 5))
            candles.append(
                CandleClosed(
                    candle_time=t,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=1.0,
                )
            )
        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, self.series_id, candles)
            conn.commit()
        with overlay_store.connect() as conn:
            overlay_store.upsert_head_time_in_conn(conn, series_id=self.series_id, head_time=candles[-1].candle_time)
            conn.commit()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_REPLAY_PACKAGE",
            "TRADE_CANVAS_ARTIFACTS_DIR",
        ):
            os.environ.pop(k, None)

    def test_replay_overlay_package_build_and_window(self) -> None:
        build = self.client.post(
            "/api/replay/overlay_package/build",
            json={"series_id": self.series_id},
        )
        self.assertEqual(build.status_code, 200, build.text)
        build_payload = build.json()
        self.assertIn(build_payload["status"], ("building", "done"))
        job_id = build_payload["job_id"]

        status = None
        for _ in range(50):
            res = self.client.get(
                "/api/replay/overlay_package/status",
                params={"job_id": job_id},
            )
            self.assertEqual(res.status_code, 200, res.text)
            status = res.json()
            if status["status"] == "done":
                break
            time.sleep(0.05)

        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status["status"], "done")
        window = self.client.get(
            "/api/replay/overlay_package/window",
            params={"job_id": job_id, "target_idx": 0},
        )
        self.assertEqual(window.status_code, 200, window.text)
        window_payload = window.json()
        self.assertEqual(window_payload["job_id"], job_id)
        self.assertIn("window", window_payload)
        self.assertEqual(window_payload["window"]["window_index"], 0)


if __name__ == "__main__":
    unittest.main()
