from __future__ import annotations

import unittest

from backend.app.factor_read_freshness import read_factor_slices_with_freshness
from backend.app.schemas import GetFactorSlicesResponseV1
from backend.app.service_errors import ServiceError


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


class ReadFactorFreshnessTests(unittest.TestCase):
    def test_read_factor_slices_with_freshness_uses_store_alignment(self) -> None:
        store = _FakeStore(aligned_time=180)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_slices_service=slices_service,
            factor_store=_FakeFactorStore(head_time=180),
            series_id="s",
            at_time=200,
            window_candles=100,
        )
        self.assertEqual(store.calls, [("s", 200)])
        self.assertEqual(slices_service.calls, [("s", 180, 200, 100)])
        self.assertEqual(payload.candle_id, "s:180")

    def test_read_factor_slices_with_freshness_respects_aligned_time_hint(self) -> None:
        store = _FakeStore(aligned_time=999)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_slices_service=slices_service,
            factor_store=_FakeFactorStore(head_time=160),
            series_id="s",
            at_time=200,
            aligned_time=160,
            window_candles=50,
        )
        self.assertEqual(store.calls, [])
        self.assertEqual(slices_service.calls, [("s", 160, 200, 50)])
        self.assertEqual(payload.candle_id, "s:160")

    def test_read_factor_slices_with_freshness_can_skip_freshness_check(self) -> None:
        store = _FakeStore(aligned_time=300)
        slices_service = _FakeSlicesService()
        payload = read_factor_slices_with_freshness(
            store=store,
            factor_slices_service=slices_service,
            factor_store=_FakeFactorStore(head_time=0),
            series_id="s",
            at_time=360,
            aligned_time=300,
            window_candles=120,
            ensure_fresh=False,
        )
        self.assertEqual(slices_service.calls, [("s", 300, 360, 120)])
        self.assertEqual(payload.candle_id, "s:300")

    def test_read_factor_slices_with_freshness_rejects_stale_factor(self) -> None:
        store = _FakeStore(aligned_time=300)
        slices_service = _FakeSlicesService()
        factor_store = _FakeFactorStore(head_time=120)
        with self.assertRaises(ServiceError) as ctx:
            read_factor_slices_with_freshness(
                store=store,
                factor_slices_service=slices_service,
                factor_store=factor_store,
                series_id="s",
                at_time=360,
                aligned_time=300,
                window_candles=120,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(slices_service.calls, [])


if __name__ == "__main__":
    unittest.main()
