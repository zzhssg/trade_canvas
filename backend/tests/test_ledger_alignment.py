from __future__ import annotations

import unittest

from backend.app.ledger.alignment import (
    LedgerAlignedPoint,
    LedgerHeadTimes,
    require_aligned_point,
    require_ledger_heads_ready,
)
from backend.app.core.service_errors import ServiceError


class _StoreStub:
    def __init__(self, *, head_time: int | None, aligned_time: int | None) -> None:
        self._head_time = head_time
        self._aligned_time = aligned_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head_time

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # noqa: ARG002
        if self._aligned_time is None:
            return None
        if int(at_time) < int(self._aligned_time):
            return None
        return int(self._aligned_time)


class _HeadStoreStub:
    def __init__(self, *, head_time: int | None) -> None:
        self._head_time = head_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head_time


class LedgerAlignmentTests(unittest.TestCase):
    def test_require_aligned_point_uses_store_head_when_to_time_is_none(self) -> None:
        point = require_aligned_point(
            store=_StoreStub(head_time=1_700_000_120, aligned_time=1_700_000_060),
            series_id="binance:futures:BTC/USDT:1m",
            to_time=None,
            no_data_code="test.no_data",
        )
        self.assertEqual(point, LedgerAlignedPoint(requested_time=1_700_000_120, aligned_time=1_700_000_060))

    def test_require_aligned_point_raises_404_when_store_has_no_data(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            require_aligned_point(
                store=_StoreStub(head_time=None, aligned_time=None),
                series_id="binance:futures:BTC/USDT:1m",
                to_time=1_700_000_120,
                no_data_code="test.no_data",
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "test.no_data")

    def test_require_aligned_point_raises_404_when_floor_time_missing(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            require_aligned_point(
                store=_StoreStub(head_time=1_700_000_120, aligned_time=None),
                series_id="binance:futures:BTC/USDT:1m",
                to_time=1_700_000_120,
                no_data_code="test.no_data",
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "test.no_data")

    def test_require_ledger_heads_ready_raises_factor_out_of_sync(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            require_ledger_heads_ready(
                factor_store=_HeadStoreStub(head_time=1_700_000_000),
                overlay_store=_HeadStoreStub(head_time=1_700_000_060),
                series_id="binance:futures:BTC/USDT:1m",
                aligned_time=1_700_000_060,
                factor_out_of_sync_code="test.factor_out_of_sync",
                overlay_out_of_sync_code="test.overlay_out_of_sync",
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "test.factor_out_of_sync")
        self.assertEqual(ctx.exception.detail, "ledger_out_of_sync:factor")

    def test_require_ledger_heads_ready_raises_overlay_out_of_sync(self) -> None:
        with self.assertRaises(ServiceError) as ctx:
            require_ledger_heads_ready(
                factor_store=_HeadStoreStub(head_time=1_700_000_060),
                overlay_store=_HeadStoreStub(head_time=1_700_000_000),
                series_id="binance:futures:BTC/USDT:1m",
                aligned_time=1_700_000_060,
                factor_out_of_sync_code="test.factor_out_of_sync",
                overlay_out_of_sync_code="test.overlay_out_of_sync",
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "test.overlay_out_of_sync")
        self.assertEqual(ctx.exception.detail, "ledger_out_of_sync:overlay")

    def test_require_ledger_heads_ready_returns_head_times(self) -> None:
        heads = require_ledger_heads_ready(
            factor_store=_HeadStoreStub(head_time=1_700_000_060),
            overlay_store=_HeadStoreStub(head_time=1_700_000_120),
            series_id="binance:futures:BTC/USDT:1m",
            aligned_time=1_700_000_060,
            factor_out_of_sync_code="test.factor_out_of_sync",
            overlay_out_of_sync_code="test.overlay_out_of_sync",
        )
        self.assertEqual(
            heads,
            LedgerHeadTimes(factor_head_time=1_700_000_060, overlay_head_time=1_700_000_120),
        )


if __name__ == "__main__":
    unittest.main()
