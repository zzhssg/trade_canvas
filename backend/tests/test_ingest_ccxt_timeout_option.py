from __future__ import annotations

import os
import types
import unittest
from unittest.mock import patch

from backend.app.ccxt_client import _make_exchange_client
from backend.app.flags import resolve_env_int
from backend.app.series_id import parse_series_id


class IngestCcxtTimeoutOptionTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("TRADE_CANVAS_CCXT_TIMEOUT_MS", None)

    def test_make_exchange_client_sets_timeout_ms(self) -> None:
        calls: list[tuple[str, dict]] = []

        def _mk(name: str):
            def _ctor(options: dict):
                calls.append((name, dict(options)))
                return object()

            return _ctor

        fake_ccxt = types.SimpleNamespace(binance=_mk("spot"), binanceusdm=_mk("futures"))

        os.environ["TRADE_CANVAS_CCXT_TIMEOUT_MS"] = "12345"
        series = parse_series_id("binance:futures:BTC/USDT:1m")
        timeout_ms = resolve_env_int("TRADE_CANVAS_CCXT_TIMEOUT_MS", fallback=10_000, minimum=1000)

        with patch.dict("sys.modules", {"ccxt": fake_ccxt}):
            _make_exchange_client(series, timeout_ms=timeout_ms)

        self.assertEqual(len(calls), 1)
        name, options = calls[0]
        self.assertEqual(name, "futures")
        self.assertTrue(options.get("enableRateLimit"))
        self.assertEqual(int(options.get("timeout")), 12345)
