from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from backend.app.replay_prepare_service import ReplayPrepareService
from backend.app.schemas import ReplayPrepareRequestV1


class _StoreStub:
    def __init__(self, *, head_time: int | None, aligned_time: int | None) -> None:
        self._head_time = head_time
        self._aligned_time = aligned_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head_time

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # noqa: ARG002
        aligned = self._aligned_time
        if aligned is None:
            return None
        return int(aligned) if int(at_time) >= int(aligned) else None


class _HeadStoreStub:
    def __init__(self, *, head_time: int | None) -> None:
        self.head_time_value = head_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self.head_time_value


class _PipelineStub:
    def __init__(self, on_refresh=None) -> None:
        self.calls: list[dict[str, int]] = []
        self._on_refresh = on_refresh

    def refresh_series_sync(self, *, up_to_times: dict[str, int]):
        self.calls.append(dict(up_to_times))
        if self._on_refresh is not None:
            self._on_refresh(dict(up_to_times))
        return SimpleNamespace(steps=[{"name": "refresh"}])


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


class ReplayPrepareServiceTests(unittest.TestCase):
    def test_prepare_returns_404_when_store_has_no_data(self) -> None:
        service = ReplayPrepareService(
            store=_StoreStub(head_time=None, aligned_time=None),
            factor_store=_HeadStoreStub(head_time=None),
            overlay_store=_HeadStoreStub(head_time=None),
            ingest_pipeline=_PipelineStub(),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )
        with self.assertRaises(HTTPException) as ctx:
            service.prepare(
                ReplayPrepareRequestV1(series_id="binance:futures:BTC/USDT:1m", to_time=1_700_000_000, window_candles=2000)
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no_data")

    def test_prepare_refreshes_stale_ledger_and_returns_success(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        factor_store = _HeadStoreStub(head_time=1_699_999_940)
        overlay_store = _HeadStoreStub(head_time=1_699_999_940)

        def _promote_heads(up_to_times: dict[str, int]) -> None:
            new_head = int(up_to_times[series_id])
            factor_store.head_time_value = new_head
            overlay_store.head_time_value = new_head

        pipeline = _PipelineStub(on_refresh=_promote_heads)
        debug_hub = _DebugHubStub()
        service = ReplayPrepareService(
            store=_StoreStub(head_time=1_700_000_060, aligned_time=1_700_000_060),
            factor_store=factor_store,
            overlay_store=overlay_store,
            ingest_pipeline=pipeline,
            debug_hub=debug_hub,
            debug_api_enabled=True,
        )

        resp = service.prepare(
            ReplayPrepareRequestV1(series_id=series_id, to_time=1_700_000_060, window_candles=1)
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.series_id, series_id)
        self.assertEqual(resp.aligned_time, 1_700_000_060)
        self.assertEqual(resp.window_candles, 100)
        self.assertTrue(resp.computed)
        self.assertEqual(pipeline.calls, [{series_id: 1_700_000_060}])
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0]["event"], "read.http.replay_prepare")

    def test_prepare_raises_409_when_factor_still_out_of_sync(self) -> None:
        service = ReplayPrepareService(
            store=_StoreStub(head_time=1_700_000_060, aligned_time=1_700_000_060),
            factor_store=_HeadStoreStub(head_time=1_700_000_000),
            overlay_store=_HeadStoreStub(head_time=1_700_000_060),
            ingest_pipeline=_PipelineStub(),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )
        with self.assertRaises(HTTPException) as ctx:
            service.prepare(
                ReplayPrepareRequestV1(
                    series_id="binance:futures:BTC/USDT:1m",
                    to_time=1_700_000_060,
                    window_candles=2000,
                )
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "ledger_out_of_sync:factor")


if __name__ == "__main__":
    unittest.main()
