from __future__ import annotations

import unittest

from fastapi import HTTPException

from backend.app.read_models.world_read_service import WorldReadService
from backend.app.schemas import DrawCursorV1, DrawDeltaV1, GetFactorSlicesResponseV1


class _StoreStub:
    def __init__(self, *, head_time: int | None, floor_time: int | None) -> None:
        self._head_time = head_time
        self._floor_time = floor_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head_time

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # noqa: ARG002
        floor = self._floor_time
        if floor is None:
            return None
        return int(floor) if int(at_time) >= int(floor) else None


class _OverlayStoreStub:
    def __init__(self, *, head_time: int | None) -> None:
        self._head_time = head_time

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head_time


class _FactorReadServiceStub:
    def __init__(self, result: GetFactorSlicesResponseV1) -> None:
        self._result = result
        self.calls: list[dict] = []

    def read_slices(self, *, series_id: str, at_time: int, window_candles: int, aligned_time=None, ensure_fresh=True):  # noqa: ANN001, ARG002
        self.calls.append({"series_id": series_id, "at_time": int(at_time), "window_candles": int(window_candles)})
        return self._result


class _DrawReadServiceStub:
    def __init__(self, result: DrawDeltaV1) -> None:
        self._result = result
        self.calls: list[dict] = []

    def read_delta(self, *, series_id: str, cursor_version_id: int, window_candles: int, at_time: int | None = None) -> DrawDeltaV1:
        self.calls.append(
            {
                "series_id": series_id,
                "cursor_version_id": int(cursor_version_id),
                "window_candles": int(window_candles),
                "at_time": None if at_time is None else int(at_time),
            }
        )
        return self._result


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


def _factor_slices(*, series_id: str, at_time: int, candle_id: str) -> GetFactorSlicesResponseV1:
    return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=candle_id)


def _draw_delta(*, series_id: str, candle_id: str | None, candle_time: int | None, next_id: int) -> DrawDeltaV1:
    return DrawDeltaV1(
        series_id=series_id,
        to_candle_id=candle_id,
        to_candle_time=candle_time,
        active_ids=[],
        instruction_catalog_patch=[],
        series_points={},
        next_cursor=DrawCursorV1(version_id=int(next_id), point_time=None),
    )


class WorldReadServiceTests(unittest.TestCase):
    def test_read_frame_live_returns_state_and_emits_debug_event(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        aligned_time = 840
        debug_hub = _DebugHubStub()
        service = WorldReadService(
            store=_StoreStub(head_time=900, floor_time=aligned_time),
            overlay_store=_OverlayStoreStub(head_time=aligned_time),
            factor_read_service=_FactorReadServiceStub(
                _factor_slices(series_id=series_id, at_time=aligned_time, candle_id=f"{series_id}:{aligned_time}")
            ),
            draw_read_service=_DrawReadServiceStub(
                _draw_delta(series_id=series_id, candle_id=f"{series_id}:{aligned_time}", candle_time=aligned_time, next_id=7)
            ),
            debug_hub=debug_hub,
            debug_api_enabled=True,
        )

        payload = service.read_frame_live(series_id=series_id, window_candles=2000)
        self.assertEqual(payload.time.at_time, 900)
        self.assertEqual(payload.time.aligned_time, aligned_time)
        self.assertEqual(payload.time.candle_id, f"{series_id}:{aligned_time}")
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0]["event"], "read.http.world_frame_live")

    def test_read_frame_at_time_raises_409_when_components_not_aligned(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        service = WorldReadService(
            store=_StoreStub(head_time=900, floor_time=840),
            overlay_store=_OverlayStoreStub(head_time=840),
            factor_read_service=_FactorReadServiceStub(
                _factor_slices(series_id=series_id, at_time=840, candle_id=f"{series_id}:840")
            ),
            draw_read_service=_DrawReadServiceStub(
                _draw_delta(series_id=series_id, candle_id=f"{series_id}:780", candle_time=780, next_id=9)
            ),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )
        with self.assertRaises(HTTPException) as ctx:
            service.read_frame_at_time(series_id=series_id, at_time=845, window_candles=2000)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "ledger_out_of_sync")

    def test_poll_delta_returns_empty_when_cursor_not_advanced(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        service = WorldReadService(
            store=_StoreStub(head_time=900, floor_time=840),
            overlay_store=_OverlayStoreStub(head_time=840),
            factor_read_service=_FactorReadServiceStub(
                _factor_slices(series_id=series_id, at_time=840, candle_id=f"{series_id}:840")
            ),
            draw_read_service=_DrawReadServiceStub(
                _draw_delta(series_id=series_id, candle_id=f"{series_id}:840", candle_time=840, next_id=3)
            ),
            debug_hub=_DebugHubStub(),
            debug_api_enabled=False,
        )

        payload = service.poll_delta(series_id=series_id, after_id=3, limit=2000, window_candles=2000)
        self.assertEqual(payload.records, [])
        self.assertEqual(payload.next_cursor.id, 3)

    def test_poll_delta_returns_record_with_factor_slices(self) -> None:
        series_id = "binance:futures:BTC/USDT:1m"
        debug_hub = _DebugHubStub()
        service = WorldReadService(
            store=_StoreStub(head_time=900, floor_time=840),
            overlay_store=_OverlayStoreStub(head_time=840),
            factor_read_service=_FactorReadServiceStub(
                _factor_slices(series_id=series_id, at_time=840, candle_id=f"{series_id}:840")
            ),
            draw_read_service=_DrawReadServiceStub(
                _draw_delta(series_id=series_id, candle_id=f"{series_id}:840", candle_time=840, next_id=4)
            ),
            debug_hub=debug_hub,
            debug_api_enabled=True,
        )

        payload = service.poll_delta(series_id=series_id, after_id=0, limit=2000, window_candles=2000)
        self.assertEqual(len(payload.records), 1)
        rec = payload.records[0]
        self.assertEqual(rec.id, 4)
        self.assertEqual(rec.to_candle_id, f"{series_id}:840")
        self.assertIsNotNone(rec.factor_slices)
        self.assertEqual(rec.factor_slices.candle_id, f"{series_id}:840")
        self.assertEqual(payload.next_cursor.id, 4)
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0]["event"], "read.http.world_delta_poll")


if __name__ == "__main__":
    unittest.main()
