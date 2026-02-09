from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.app.factor_orchestrator import FactorOrchestrator, FactorSettings
from backend.app.factor_store import FactorStore
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


if __name__ == "__main__":
    unittest.main()
