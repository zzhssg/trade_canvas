from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import create_app


class BacktestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        (root / "user_data").mkdir(parents=True, exist_ok=True)

        self.config_path = root / "config.json"
        self.config_path.write_text('{"trading_mode":"futures","stake_currency":"USDT","datadir":"user_data/data"}', encoding="utf-8")

        # Provide a minimal OHLCV fixture so /api/backtest/run passes the "data availability" preflight.
        # The API checks for files relative to the configured datadir (not exchange subdir in this fixture).
        futures_dir = root / "user_data" / "data" / "futures"
        futures_dir.mkdir(parents=True, exist_ok=True)
        (futures_dir / "BTC_USDT_USDT-1h-futures.feather").write_bytes(b"")

        os.environ["TRADE_CANVAS_FREQTRADE_ROOT"] = str(root)
        os.environ["TRADE_CANVAS_FREQTRADE_CONFIG"] = str(self.config_path)
        os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
        os.environ["TRADE_CANVAS_BACKTEST_REQUIRE_TRADES"] = "0"
        (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")

        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_FREQTRADE_ROOT",
            "TRADE_CANVAS_FREQTRADE_CONFIG",
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_BACKTEST_REQUIRE_TRADES",
        ):
            os.environ.pop(key, None)

    def test_strategies_endpoint_parses_stdout(self) -> None:
        from backend.app.freqtrade_runner import FreqtradeExecResult

        with patch(
            "backend.app.main.list_strategies_async",
            new=AsyncMock(
                return_value=FreqtradeExecResult(
                ok=True,
                exit_code=0,
                duration_ms=1,
                command=["freqtrade", "list-strategies"],
                stdout="Zeta\nAlpha\n\nnot-a-strategy\n",
                stderr="",
                )
            ),
        ):
            resp = self.client.get("/api/backtest/strategies")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["strategies"], ["Alpha", "Zeta"])

    def test_run_backtest_requires_known_strategy(self) -> None:
        from backend.app.freqtrade_runner import FreqtradeExecResult

        with patch(
            "backend.app.main.list_strategies_async",
            new=AsyncMock(
                return_value=FreqtradeExecResult(
                ok=True,
                exit_code=0,
                duration_ms=1,
                command=["freqtrade", "list-strategies"],
                stdout="KnownStrategy\n",
                stderr="",
                )
            ),
        ):
            resp = self.client.post(
                "/api/backtest/run",
                json={"strategy_name": "MissingStrategy", "pair": "BTC/USDT", "timeframe": "1h"},
            )
            self.assertEqual(resp.status_code, 404)

    def test_run_backtest_appends_futures_pair_suffix(self) -> None:
        from backend.app.freqtrade_runner import FreqtradeExecResult

        list_ok = FreqtradeExecResult(
            ok=True,
            exit_code=0,
            duration_ms=1,
            command=["freqtrade", "list-strategies"],
            stdout="KnownStrategy\n",
            stderr="",
        )
        run_ok = FreqtradeExecResult(
            ok=True,
            exit_code=0,
            duration_ms=12,
            command=["freqtrade", "backtesting"],
            stdout="ok",
            stderr="",
        )

        with patch("backend.app.main.list_strategies_async", new=AsyncMock(return_value=list_ok)), patch(
            "backend.app.main.run_backtest_async", new=AsyncMock(return_value=run_ok)
        ) as mock_run:
            resp = self.client.post(
                "/api/backtest/run",
                json={"strategy_name": "KnownStrategy", "pair": "BTC/USDT", "timeframe": "1h"},
            )
            self.assertEqual(resp.status_code, 200)
            # trading_mode=futures in config fixture => BTC/USDT should become BTC/USDT:USDT
            called_kwargs = mock_run.call_args.kwargs
            self.assertEqual(called_kwargs["pair"], "BTC/USDT:USDT")

    def test_run_backtest_prints_stdout_and_stderr(self) -> None:
        from backend.app.freqtrade_runner import FreqtradeExecResult

        list_ok = FreqtradeExecResult(
            ok=True,
            exit_code=0,
            duration_ms=1,
            command=["freqtrade", "list-strategies"],
            stdout="KnownStrategy\n",
            stderr="",
        )
        run_ok = FreqtradeExecResult(
            ok=True,
            exit_code=0,
            duration_ms=12,
            command=["freqtrade", "backtesting"],
            stdout="BACKTEST REPORT",
            stderr="WARNINGS",
        )

        with patch("backend.app.main.list_strategies_async", new=AsyncMock(return_value=list_ok)), patch(
            "backend.app.main.run_backtest_async", new=AsyncMock(return_value=run_ok)
        ), patch("backend.app.main.logger") as mock_logger:
            resp = self.client.post(
                "/api/backtest/run",
                json={"strategy_name": "KnownStrategy", "pair": "BTC/USDT", "timeframe": "1h"},
            )
            self.assertEqual(resp.status_code, 200)
            # Must print (log) both stdout and stderr when present.
            info_calls = " ".join(str(c.args[0]) for c in mock_logger.info.call_args_list)
            self.assertIn("freqtrade backtesting stdout", info_calls)
            self.assertIn("freqtrade backtesting stderr", info_calls)


if __name__ == "__main__":
    unittest.main()
