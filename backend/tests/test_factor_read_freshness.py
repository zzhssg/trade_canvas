from __future__ import annotations

import unittest
from dataclasses import dataclass

from backend.app.factor_read_freshness import ensure_factor_fresh_for_read, read_factor_slices_with_freshness


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


class _FakeStore:
    def __init__(self, aligned_time: int | None) -> None:
        self.aligned_time = aligned_time
        self.calls: list[tuple[str, int]] = []

    def floor_time(self, series_id: str, at_time: int) -> int | None:
        self.calls.append((str(series_id), int(at_time)))
        return self.aligned_time


class _FakeSlicesService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, int, int]] = []

    def get_slices_aligned(
        self,
        *,
        series_id: str,
        aligned_time: int | None,
        at_time: int,
        window_candles: int,
    ) -> dict:
        self.calls.append((str(series_id), aligned_time, int(at_time), int(window_candles)))
        return {"series_id": str(series_id), "aligned_time": aligned_time, "at_time": int(at_time)}


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

    def test_read_factor_slices_with_freshness_uses_store_alignment_and_runs_ingest(self) -> None:
        store = _FakeStore(aligned_time=180)
        orchestrator = _FakeOrchestrator(rebuilt=False)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=orchestrator,
            factor_slices_service=slices_service,
            series_id="s",
            at_time=200,
            window_candles=100,
        )
        self.assertEqual(store.calls, [("s", 200)])
        self.assertEqual(orchestrator.calls, [("s", 180)])
        self.assertEqual(slices_service.calls, [("s", 180, 200, 100)])
        self.assertEqual(payload["aligned_time"], 180)

    def test_read_factor_slices_with_freshness_respects_aligned_time_hint(self) -> None:
        store = _FakeStore(aligned_time=999)
        orchestrator = _FakeOrchestrator(rebuilt=True)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=orchestrator,
            factor_slices_service=slices_service,
            series_id="s",
            at_time=200,
            aligned_time=160,
            window_candles=50,
        )
        self.assertEqual(store.calls, [])
        self.assertEqual(orchestrator.calls, [("s", 160)])
        self.assertEqual(slices_service.calls, [("s", 160, 200, 50)])
        self.assertEqual(payload["aligned_time"], 160)

    def test_read_factor_slices_with_freshness_can_skip_ingest(self) -> None:
        store = _FakeStore(aligned_time=300)
        orchestrator = _FakeOrchestrator(rebuilt=True)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=orchestrator,
            factor_slices_service=slices_service,
            series_id="s",
            at_time=360,
            aligned_time=300,
            window_candles=120,
            ensure_fresh=False,
        )
        self.assertEqual(orchestrator.calls, [])
        self.assertEqual(slices_service.calls, [("s", 300, 360, 120)])
        self.assertEqual(payload["aligned_time"], 300)


if __name__ == "__main__":
    unittest.main()
