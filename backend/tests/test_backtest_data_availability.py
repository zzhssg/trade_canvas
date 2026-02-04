from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import create_app


class BacktestDataAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)

        # Minimal freqtrade config fixture.
        datadir = root / "data" / "binance"
        (datadir / "futures").mkdir(parents=True, exist_ok=True)
        # Provide only 1m futures data so 4h is missing.
        (datadir / "futures" / "BTC_USDT_USDT-1m-futures.feather").write_bytes(b"")

        cfg = {
            "trading_mode": "futures",
            "margin_mode": "isolated",
            "stake_currency": "USDT",
            "datadir": str(datadir),
            "exchange": {
                "name": "binance",
                "ccxt_config": {},
                "ccxt_async_config": {},
                "pair_whitelist": ["BTC/USDT:USDT"],
                "pair_blacklist": [],
            },
            "pairlists": [{"method": "StaticPairList"}],
        }
        self.config_path = root / "config.json"
        import json

        self.config_path.write_text(json.dumps(cfg), encoding="utf-8")

        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")
        os.environ["TRADE_CANVAS_FREQTRADE_CONFIG"] = str(self.config_path)
        os.environ["TRADE_CANVAS_FREQTRADE_ROOT"] = str(root)

        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_FREQTRADE_CONFIG",
            "TRADE_CANVAS_FREQTRADE_ROOT",
        ):
            os.environ.pop(k, None)

    def test_pair_timeframes_lists_available(self) -> None:
        resp = self.client.get("/api/backtest/pair_timeframes", params={"pair": "BTC/USDT"})
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["pair"], "BTC/USDT")
        self.assertEqual(payload["trading_mode"], "futures")
        self.assertIn("1m", payload["available_timeframes"])

    def test_run_backtest_fails_fast_when_data_missing(self) -> None:
        from backend.app.freqtrade_runner import FreqtradeExecResult

        list_ok = FreqtradeExecResult(
            ok=True,
            exit_code=0,
            duration_ms=1,
            command=["freqtrade", "list-strategies"],
            stdout="TradeCanvasMinimalStrategy\n",
            stderr="",
        )

        with patch("backend.app.main.list_strategies_async", new=AsyncMock(return_value=list_ok)), patch(
            "backend.app.main.run_backtest_async", new=AsyncMock()
        ) as mock_run:
            resp = self.client.post(
                "/api/backtest/run",
                json={"strategy_name": "TradeCanvasMinimalStrategy", "pair": "BTC/USDT", "timeframe": "4h"},
            )
            self.assertEqual(resp.status_code, 422, resp.text)
            detail = resp.json()["detail"]
            self.assertEqual(detail["message"], "no_ohlcv_history")
            self.assertEqual(detail["timeframe"], "4h")
            self.assertIn("BTC/USDT:USDT", detail["pair"])
            self.assertIn("expected_paths", detail)
            self.assertIn("available_timeframes", detail)
            self.assertIn("1m", detail["available_timeframes"])
            mock_run.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

