from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.app.replay.prepare_service import ReplayPrepareService
from backend.app.core.schemas import ReplayPrepareRequestV1
from backend.app.core.service_errors import ServiceError


class _LedgerSyncStub:
    def __init__(
        self,
        *,
        point_time: int = 1_700_000_060,
        refresh_refreshed: bool = False,
        heads_factor_time: int = 1_700_000_060,
        heads_overlay_time: int = 1_700_000_060,
        resolve_error: ServiceError | None = None,
        heads_error: ServiceError | None = None,
    ) -> None:
        self.point_time = int(point_time)
        self.refresh_refreshed = bool(refresh_refreshed)
        self.heads_factor_time = int(heads_factor_time)
        self.heads_overlay_time = int(heads_overlay_time)
        self.resolve_error = resolve_error
        self.heads_error = heads_error
        self.refresh_calls: list[tuple[str, int]] = []

    def resolve_aligned_point(
        self,
        *,
        series_id: str,
        to_time: int | None,
        no_data_code: str,
        no_data_detail: str = "no_data",
    ):
        _ = series_id
        _ = to_time
        _ = no_data_code
        _ = no_data_detail
        if self.resolve_error is not None:
            raise self.resolve_error
        return SimpleNamespace(
            requested_time=int(self.point_time),
            aligned_time=int(self.point_time),
        )

    def refresh_if_needed(self, *, series_id: str, up_to_time: int):
        self.refresh_calls.append((str(series_id), int(up_to_time)))
        return SimpleNamespace(refreshed=bool(self.refresh_refreshed))

    def require_heads_ready(
        self,
        *,
        series_id: str,
        aligned_time: int,
        factor_out_of_sync_code: str,
        overlay_out_of_sync_code: str,
        factor_out_of_sync_detail: str = "ledger_out_of_sync:factor",
        overlay_out_of_sync_detail: str = "ledger_out_of_sync:overlay",
    ):
        _ = series_id
        _ = aligned_time
        _ = factor_out_of_sync_code
        _ = overlay_out_of_sync_code
        _ = factor_out_of_sync_detail
        _ = overlay_out_of_sync_detail
        if self.heads_error is not None:
            raise self.heads_error
        return SimpleNamespace(
            factor_head_time=int(self.heads_factor_time),
            overlay_head_time=int(self.heads_overlay_time),
        )


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


class ReplayPrepareServiceTests(unittest.TestCase):
    def test_prepare_returns_404_when_store_has_no_data(self) -> None:
        service = ReplayPrepareService(
            ledger_sync_service=_LedgerSyncStub(
                resolve_error=ServiceError(
                    status_code=404,
                    detail="no_data",
                    code="replay_prepare.no_data",
                )
            ),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )
        with self.assertRaises(ServiceError) as ctx:
            service.prepare(
                ReplayPrepareRequestV1(series_id="binance:futures:BTC/USDT:1m", to_time=1_700_000_000, window_candles=2000)
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no_data")

    def test_prepare_refreshes_stale_ledger_and_returns_success(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        ledger_sync = _LedgerSyncStub(
            point_time=1_700_000_060,
            refresh_refreshed=True,
            heads_factor_time=1_700_000_060,
            heads_overlay_time=1_700_000_060,
        )
        debug_hub = _DebugHubStub()
        service = ReplayPrepareService(
            ledger_sync_service=ledger_sync,
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
        self.assertEqual(ledger_sync.refresh_calls, [(series_id, 1_700_000_060)])
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0]["event"], "read.http.replay_prepare")

    def test_prepare_raises_409_when_factor_still_out_of_sync(self) -> None:
        service = ReplayPrepareService(
            ledger_sync_service=_LedgerSyncStub(
                heads_error=ServiceError(
                    status_code=409,
                    detail="ledger_out_of_sync:factor",
                    code="replay_prepare.ledger_out_of_sync.factor",
                )
            ),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )
        with self.assertRaises(ServiceError) as ctx:
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
