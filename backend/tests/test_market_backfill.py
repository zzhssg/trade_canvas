from __future__ import annotations

import unittest
from unittest import mock

from backend.app.market.backfill import backfill_market_gap_best_effort


class _StoreStub:
    def __init__(self, *, counts: list[int]) -> None:
        self._counts = list(counts)
        self._idx = 0
        self.calls: list[tuple[str, int, int]] = []

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        self.calls.append((str(series_id), int(start_time), int(end_time)))
        if self._idx >= len(self._counts):
            return int(self._counts[-1] if self._counts else 0)
        value = int(self._counts[self._idx])
        self._idx += 1
        return value


class MarketBackfillTests(unittest.TestCase):
    def test_gap_backfill_logs_warning_when_freqtrade_bootstrap_fails(self) -> None:
        store = _StoreStub(counts=[0, 0])
        with mock.patch(
            "backend.app.market.backfill.backfill_tail_from_freqtrade",
            side_effect=RuntimeError("freqtrade_down"),
        ):
            with self.assertLogs("backend.app.market.backfill", level="WARNING") as logs:
                filled = backfill_market_gap_best_effort(
                    store=store,
                    series_id="binance:futures:BTC/USDT:1m",
                    expected_next_time=120,
                    actual_time=240,
                    enable_ccxt_backfill=False,
                    market_history_source="",
                )

        self.assertEqual(filled, 0)
        self.assertEqual(len(store.calls), 2)
        self.assertTrue(any("market_gap_backfill_freqtrade_failed" in line for line in logs.output))

    def test_gap_backfill_logs_warning_when_ccxt_fallback_fails(self) -> None:
        store = _StoreStub(counts=[2, 2])
        with mock.patch("backend.app.market.backfill.backfill_tail_from_freqtrade", return_value=None):
            with mock.patch(
                "backend.app.market.backfill.backfill_from_ccxt_range",
                side_effect=RuntimeError("ccxt_down"),
            ):
                with self.assertLogs("backend.app.market.backfill", level="WARNING") as logs:
                    filled = backfill_market_gap_best_effort(
                        store=store,
                        series_id="binance:futures:BTC/USDT:1m",
                        expected_next_time=120,
                        actual_time=240,
                        enable_ccxt_backfill=True,
                        ccxt_timeout_ms=3000,
                        market_history_source="",
                    )

        self.assertEqual(filled, 0)
        self.assertEqual(len(store.calls), 2)
        self.assertTrue(any("market_gap_backfill_ccxt_failed" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
