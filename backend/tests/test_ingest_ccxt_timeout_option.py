from __future__ import annotations

import os
import types
import unittest
from unittest.mock import patch

from backend.app.market.ccxt_client import _make_exchange_client
from backend.app.core.flags import resolve_env_int
from backend.app.core.series_id import parse_series_id


class IngestCcxtTimeoutOptionTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("TRADE_CANVAS_CCXT_TIMEOUT_MS", None)

    def test_make_exchange_client_sets_timeout_ms(self) -> None:
        calls: list[tuple[str, dict, types.SimpleNamespace]] = []

        def _mk(name: str):
            def _ctor(options: dict):
                session = types.SimpleNamespace(trust_env=False)
                calls.append((name, dict(options), session))
                return types.SimpleNamespace(session=session)

            return _ctor

        fake_ccxt = types.SimpleNamespace(binance=_mk("spot"), binanceusdm=_mk("futures"))

        os.environ["TRADE_CANVAS_CCXT_TIMEOUT_MS"] = "12345"
        series = parse_series_id("binance:futures:BTC/USDT:1m")
        timeout_ms = resolve_env_int("TRADE_CANVAS_CCXT_TIMEOUT_MS", fallback=10_000, minimum=1000)

        with patch.dict("sys.modules", {"ccxt": fake_ccxt}):
            _make_exchange_client(series, timeout_ms=timeout_ms)

        self.assertEqual(len(calls), 1)
        name, options, session = calls[0]
        self.assertEqual(name, "futures")
        self.assertTrue(options.get("enableRateLimit"))
        timeout = options.get("timeout")
        self.assertIsNotNone(timeout)
        assert timeout is not None
        self.assertEqual(int(timeout), 12345)
        self.assertTrue(bool(session.trust_env))
