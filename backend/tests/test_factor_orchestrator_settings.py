from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.factor_orchestrator import FactorOrchestrator, FactorSettings
from backend.app.factor_store import FactorEventRow, FactorStore
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class FactorOrchestratorSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.orchestrator = FactorOrchestrator(
            candle_store=CandleStore(self.db_path),
            factor_store=FactorStore(self.db_path),
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_FACTOR_LOGIC_VERSION",
        ):
            os.environ.pop(key, None)

    def test_load_settings_reads_state_rebuild_event_limit(self) -> None:
        os.environ["TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT"] = "3200"
        settings = self.orchestrator._load_settings()
        self.assertEqual(settings.state_rebuild_event_limit, 3200)

    def test_load_settings_clamps_state_rebuild_event_limit(self) -> None:
        os.environ["TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT"] = "9"
        settings = self.orchestrator._load_settings()
        self.assertEqual(settings.state_rebuild_event_limit, 1000)

    def test_fingerprint_includes_state_rebuild_event_limit(self) -> None:
        s1 = FactorSettings(state_rebuild_event_limit=50000)
        s2 = FactorSettings(state_rebuild_event_limit=80000)
        fp1 = self.orchestrator._build_series_fingerprint(series_id="binance:futures:BTC/USDT:1m", settings=s1)
        fp2 = self.orchestrator._build_series_fingerprint(series_id="binance:futures:BTC/USDT:1m", settings=s2)
        self.assertNotEqual(fp1, fp2)

    def test_state_rebuild_uses_paged_scan_after_limit_hit(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "100"
        os.environ["TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT"] = "1000"
        series_id = "binance:futures:BTC/USDT:1m"

        self.orchestrator._candle_store.upsert_closed(
            series_id,
            CandleClosed(candle_time=60, open=100, high=101, low=99, close=100, volume=1),
        )
        self.orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=60)

        self.orchestrator._candle_store.upsert_closed(
            series_id,
            CandleClosed(candle_time=120, open=100, high=101, low=99, close=100, volume=1),
        )

        fake_rows = [
            FactorEventRow(
                id=i + 1,
                series_id=series_id,
                factor_name="pivot",
                candle_time=60,
                kind="pivot.major",
                event_key=f"k:{i}",
                payload={},
            )
            for i in range(1000)
        ]
        with (
            patch.object(FactorStore, "get_events_between_times", return_value=fake_rows) as base_scan,
            patch.object(FactorStore, "get_events_between_times_paged", return_value=[]) as paged_scan,
        ):
            self.orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=120)

        self.assertTrue(base_scan.called)
        self.assertTrue(paged_scan.called)


if __name__ == "__main__":
    unittest.main()
