from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.pipelines import IngestPipelineError


class _FailingIngestPipeline:
    def __init__(self, *, series_id: str) -> None:
        self._series_id = str(series_id)

    async def run(self, *, batches, publish: bool = True):
        _ = batches
        _ = publish
        raise IngestPipelineError(
            step="overlay.ingest_closed",
            series_id=self._series_id,
            cause=RuntimeError("overlay_failed"),
            compensated=True,
            overlay_compensated=True,
            candle_compensated_rows=2,
        )


class MarketIngestErrorObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.client.close()
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        os.environ.pop("TRADE_CANVAS_ENABLE_DEBUG_API", None)

    def test_ingest_pipeline_error_is_mapped_and_debug_event_exposes_compensation(self) -> None:
        app = cast(Any, self.client.app)
        runtime = app.state.container.market_runtime
        runtime.ingest._ingest_pipeline = _FailingIngestPipeline(series_id=self.series_id)  # type: ignore[attr-defined]

        response = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": 180, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            },
        )

        self.assertEqual(response.status_code, 500, response.text)
        payload = response.json()
        self.assertEqual(payload["detail"], f"ingest_pipeline_failed:overlay.ingest_closed:{self.series_id}")

        events = runtime.debug_hub.snapshot()
        error_events = [event for event in events if event.get("event") == "write.http.ingest_candle_closed_error"]
        self.assertTrue(error_events)
        data = error_events[-1].get("data") or {}
        self.assertEqual(data.get("step"), "overlay.ingest_closed")
        self.assertEqual(data.get("series_id"), self.series_id)
        self.assertTrue(bool(data.get("compensated")))
        self.assertTrue(bool(data.get("overlay_compensated")))
        self.assertEqual(data.get("candle_compensated_rows"), 2)


if __name__ == "__main__":
    unittest.main()
