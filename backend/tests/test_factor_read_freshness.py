from __future__ import annotations

import unittest
from dataclasses import dataclass

from backend.app.factor_read_freshness import ensure_factor_fresh_for_read


@dataclass(frozen=True)
class _FakeResult:
    rebuilt: bool


class _FakeOrchestrator:
    def __init__(self, rebuilt: bool) -> None:
        self.rebuilt = bool(rebuilt)
        self.calls: list[tuple[str, int]] = []

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> _FakeResult:
        self.calls.append((str(series_id), int(up_to_candle_time)))
        return _FakeResult(rebuilt=self.rebuilt)


class EnsureFactorFreshForReadTests(unittest.TestCase):
    def test_rejects_missing_or_non_positive_up_to_time(self) -> None:
        orchestrator = _FakeOrchestrator(rebuilt=True)
        self.assertFalse(
            ensure_factor_fresh_for_read(
                factor_orchestrator=orchestrator,
                series_id="s",
                up_to_time=None,
            )
        )
        self.assertFalse(
            ensure_factor_fresh_for_read(
                factor_orchestrator=orchestrator,
                series_id="s",
                up_to_time=0,
            )
        )
        self.assertEqual(orchestrator.calls, [])

    def test_calls_orchestrator_and_returns_rebuilt_flag(self) -> None:
        orchestrator = _FakeOrchestrator(rebuilt=True)
        rebuilt = ensure_factor_fresh_for_read(
            factor_orchestrator=orchestrator,
            series_id="binance:futures:BTC/USDT:1m",
            up_to_time=1700000000,
        )
        self.assertTrue(rebuilt)
        self.assertEqual(orchestrator.calls, [("binance:futures:BTC/USDT:1m", 1700000000)])


if __name__ == "__main__":
    unittest.main()
