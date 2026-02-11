from __future__ import annotations

import unittest
from dataclasses import dataclass

from backend.app.factor_read_freshness import ensure_factor_fresh_for_read, read_factor_slices_with_freshness
from backend.app.schemas import GetFactorSlicesResponseV1
from backend.app.service_errors import ServiceError


@dataclass
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

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
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
    ) -> GetFactorSlicesResponseV1:
        self.calls.append((str(series_id), aligned_time, int(at_time), int(window_candles)))
        candle_id = f"{series_id}:{int(aligned_time)}" if aligned_time is not None else None
        return GetFactorSlicesResponseV1(
            series_id=str(series_id),
            at_time=int(at_time),
            candle_id=candle_id,
        )


class _FakeFactorStore:
    def __init__(self, head_time: int | None) -> None:
        self._head_time = head_time

    def head_time(self, series_id: str) -> int | None:
        _ = series_id
        return self._head_time


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

    def test_read_factor_slices_with_freshness_uses_store_alignment_and_runs_ingest_when_enabled(self) -> None:
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
            implicit_recompute_enabled=True,
        )
        self.assertEqual(store.calls, [("s", 200)])
        self.assertEqual(orchestrator.calls, [("s", 180)])
        self.assertEqual(slices_service.calls, [("s", 180, 200, 100)])
        self.assertEqual(payload.candle_id, "s:180")

    def test_read_factor_slices_with_freshness_respects_aligned_time_hint_when_recompute_enabled(self) -> None:
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
            implicit_recompute_enabled=True,
        )
        self.assertEqual(store.calls, [])
        self.assertEqual(orchestrator.calls, [("s", 160)])
        self.assertEqual(slices_service.calls, [("s", 160, 200, 50)])
        self.assertEqual(payload.candle_id, "s:160")

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
        self.assertEqual(payload.candle_id, "s:300")

    def test_read_factor_slices_with_freshness_strict_mode_rejects_stale_factor(self) -> None:
        store = _FakeStore(aligned_time=300)
        orchestrator = _FakeOrchestrator(rebuilt=True)
        slices_service = _FakeSlicesService()
        factor_store = _FakeFactorStore(head_time=120)
        with self.assertRaises(ServiceError) as ctx:
            read_factor_slices_with_freshness(
                store=store,
                factor_orchestrator=orchestrator,
                factor_slices_service=slices_service,
                factor_store=factor_store,
                series_id="s",
                at_time=360,
                aligned_time=300,
                window_candles=120,
                strict_mode=True,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(orchestrator.calls, [])
        self.assertEqual(slices_service.calls, [])

    def test_read_factor_slices_with_freshness_non_strict_skips_auto_ingest_by_default(self) -> None:
        store = _FakeStore(aligned_time=300)
        orchestrator = _FakeOrchestrator(rebuilt=False)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=orchestrator,
            factor_slices_service=slices_service,
            series_id="s",
            at_time=360,
            aligned_time=300,
            window_candles=120,
            strict_mode=False,
        )
        self.assertEqual(orchestrator.calls, [])
        self.assertEqual(slices_service.calls, [("s", 300, 360, 120)])
        self.assertEqual(payload.candle_id, "s:300")

    def test_read_factor_slices_with_freshness_non_strict_can_enable_auto_ingest_explicitly(self) -> None:
        store = _FakeStore(aligned_time=300)
        orchestrator = _FakeOrchestrator(rebuilt=False)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=orchestrator,
            factor_slices_service=slices_service,
            series_id="s",
            at_time=360,
            aligned_time=300,
            window_candles=120,
            strict_mode=False,
            implicit_recompute_enabled=True,
        )
        self.assertEqual(orchestrator.calls, [("s", 300)])
        self.assertEqual(slices_service.calls, [("s", 300, 360, 120)])
        self.assertEqual(payload.candle_id, "s:300")


if __name__ == "__main__":
    unittest.main()
