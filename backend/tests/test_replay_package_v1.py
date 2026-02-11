from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CandleClosed


class ReplayPackageApiTests(unittest.TestCase):
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
        os.environ["TRADE_CANVAS_ENABLE_REPLAY_V1"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE"] = "1"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
            "TRADE_CANVAS_ENABLE_REPLAY_V1",
            "TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE",
        ):
            os.environ.pop(k, None)

    def _ingest(self, t: int, price: float) -> None:
        app = cast(Any, self.client.app)
        container = app.state.container
        store = container.store
        factor_orch = container.factor_orchestrator
        overlay_orch = container.overlay_orchestrator
        candle = CandleClosed(candle_time=t, open=price, high=price, low=price, close=price, volume=1)
        store.upsert_closed(self.series_id, candle)
        factor_orch.ingest_closed(series_id=self.series_id, up_to_candle_time=t)
        overlay_orch.ingest_closed(series_id=self.series_id, up_to_candle_time=t)

    def _wait_for_done(self, job_id: str, *, timeout_s: float = 5.0) -> dict:
        deadline = time.time() + timeout_s
        last_payload: dict | None = None
        while time.time() < deadline:
            res = self.client.get(
                "/api/replay/status",
                params={"job_id": job_id, "include_preload": 1, "include_history": 1},
            )
            self.assertEqual(res.status_code, 200, res.text)
            payload = res.json()
            last_payload = payload
            if payload.get("status") == "done":
                return payload
            if payload.get("status") == "error":
                self.fail(f"replay build failed: {payload}")
            time.sleep(0.05)
        self.fail(f"replay build timeout: {last_payload}")

    def test_replay_disabled_returns_404(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        os.environ["TRADE_CANVAS_ENABLE_REPLAY_V1"] = "0"
        client = TestClient(create_app())
        try:
            res = client.get("/api/replay/read_only", params={"series_id": self.series_id, "window_candles": 10})
            self.assertEqual(res.status_code, 404, res.text)
        finally:
            client.close()
        os.environ["TRADE_CANVAS_ENABLE_REPLAY_V1"] = "1"
        self.client = TestClient(create_app())

    def test_replay_build_and_window_flow(self) -> None:
        base = 60
        prices = list(range(1, 111))
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_read = self.client.get(
            "/api/replay/read_only",
            params={
                "series_id": self.series_id,
                "to_time": times[-1],
                "window_candles": 100,
                "window_size": 50,
                "snapshot_interval": 5,
            },
        )
        self.assertEqual(res_read.status_code, 200, res_read.text)
        payload_read = res_read.json()
        self.assertIn(payload_read["status"], ("build_required", "done"))
        self.assertEqual(payload_read["coverage"]["candles_ready"], 100)

        res_build = self.client.post(
            "/api/replay/build",
            json={
                "series_id": self.series_id,
                "to_time": times[-1],
                "window_candles": 100,
                "window_size": 50,
                "snapshot_interval": 5,
            },
        )
        self.assertEqual(res_build.status_code, 200, res_build.text)
        payload_build = res_build.json()
        job_id = payload_build["job_id"]
        status_payload = self._wait_for_done(job_id)

        meta = status_payload["metadata"]
        self.assertEqual(meta["series_id"], self.series_id)
        self.assertEqual(meta["total_candles"], 100)
        self.assertEqual(meta["from_candle_time"], times[10])
        self.assertEqual(meta["to_candle_time"], times[-1])
        self.assertIsNotNone(status_payload.get("preload_window"))
        self.assertIsInstance(status_payload.get("history_events"), list)

        res_window = self.client.get("/api/replay/window", params={"job_id": job_id, "target_idx": 0})
        self.assertEqual(res_window.status_code, 200, res_window.text)
        payload_window = res_window.json()
        window = payload_window["window"]
        self.assertEqual(window["window_index"], 0)
        self.assertGreater(len(window["kline"]), 0)
        self.assertGreater(len(payload_window["history_deltas"]), 0)

    def test_replay_ensure_coverage_flow(self) -> None:
        base = 60
        prices = [1, 2, 3, 4, 5, 6]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_cover = self.client.post(
            "/api/replay/ensure_coverage",
            json={"series_id": self.series_id, "target_candles": 5, "to_time": times[-1]},
        )
        self.assertEqual(res_cover.status_code, 200, res_cover.text)
        job_id = res_cover.json()["job_id"]

        deadline = time.time() + 5.0
        last = None
        while time.time() < deadline:
            res_status = self.client.get("/api/replay/coverage_status", params={"job_id": job_id})
            self.assertEqual(res_status.status_code, 200, res_status.text)
            last = res_status.json()
            if last.get("status") == "done":
                break
            if last.get("status") == "error":
                self.fail(f"coverage failed: {last}")
            time.sleep(0.05)

        self.assertIsNotNone(last)
        assert last is not None
        self.assertEqual(last["status"], "done")
        self.assertEqual(last["candles_ready"], 5)


if __name__ == "__main__":
    unittest.main()
