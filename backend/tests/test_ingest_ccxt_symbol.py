from __future__ import annotations

import unittest

from backend.app.ingest_ccxt import ccxt_symbol_for_series
from backend.app.series_id import parse_series_id


class IngestCcxtSymbolTests(unittest.TestCase):
    def test_spot_keeps_symbol(self) -> None:
        series = parse_series_id("binance:spot:BTC/USDT:1m")
        self.assertEqual(ccxt_symbol_for_series(series), "BTC/USDT")

    def test_futures_adds_colon_quote(self) -> None:
        series = parse_series_id("binance:futures:BTC/USDT:1m")
        self.assertEqual(ccxt_symbol_for_series(series), "BTC/USDT:USDT")

    def test_futures_preserves_existing_ccxt_symbol(self) -> None:
        series = parse_series_id("binance:futures:BTC/USDT:USDT:1m")
        self.assertEqual(ccxt_symbol_for_series(series), "BTC/USDT:USDT")


if __name__ == "__main__":
    unittest.main()

