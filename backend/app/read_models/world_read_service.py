from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from ..debug_hub import DebugHub
from ..schemas import (
    DrawDeltaV1,
    GetFactorSlicesResponseV1,
    WorldCursorV1,
    WorldDeltaPollResponseV1,
    WorldDeltaRecordV1,
    WorldStateV1,
    WorldTimeV1,
)


class _StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class _OverlayStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class _FactorReadServiceLike(Protocol):
    def read_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
    ) -> GetFactorSlicesResponseV1: ...


class _DrawReadServiceLike(Protocol):
    def read_delta(
        self,
        *,
        series_id: str,
        cursor_version_id: int,
        window_candles: int,
        at_time: int | None = None,
    ) -> DrawDeltaV1: ...


@dataclass(frozen=True)
class WorldReadService:
    store: _StoreLike
    overlay_store: _OverlayStoreLike
    factor_read_service: _FactorReadServiceLike
    draw_read_service: _DrawReadServiceLike
    debug_hub: DebugHub
    debug_api_enabled: bool = False

    def _debug_enabled(self) -> bool:
        return bool(self.debug_api_enabled)

    def _read_factor_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
    ) -> GetFactorSlicesResponseV1:
        return self.factor_read_service.read_slices(
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    def _read_draw_delta(
        self,
        *,
        series_id: str,
        cursor_version_id: int,
        window_candles: int,
        at_time: int | None,
    ) -> DrawDeltaV1:
        return self.draw_read_service.read_delta(
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            window_candles=int(window_candles),
            at_time=None if at_time is None else int(at_time),
        )

    @staticmethod
    def _require_matching_candle_id(
        *,
        series_id: str,
        aligned_time: int,
        factor_slices: GetFactorSlicesResponseV1,
        draw_state: DrawDeltaV1,
    ) -> str:
        candle_id = f"{series_id}:{int(aligned_time)}"
        if factor_slices.candle_id != candle_id or draw_state.to_candle_id != candle_id:
            raise HTTPException(status_code=409, detail="ledger_out_of_sync")
        return candle_id

    def _emit_frame_debug(
        self,
        *,
        event: str,
        series_id: str,
        at_time: int,
        aligned_time: int,
        candle_id: str,
    ) -> None:
        if not self._debug_enabled():
            return
        self.debug_hub.emit(
            pipe="read",
            event=event,
            series_id=series_id,
            message="get world frame",
            data={
                "at_time": int(at_time),
                "aligned_time": int(aligned_time),
                "candle_id": str(candle_id),
            },
        )

    def _build_world_state(
        self,
        *,
        series_id: str,
        at_time: int,
        aligned_time: int,
        window_candles: int,
        debug_event: str,
    ) -> WorldStateV1:
        factor_slices = self._read_factor_slices(
            series_id=series_id,
            at_time=int(aligned_time),
            window_candles=int(window_candles),
        )
        draw_state = self._read_draw_delta(
            series_id=series_id,
            cursor_version_id=0,
            window_candles=int(window_candles),
            at_time=int(aligned_time),
        )
        candle_id = self._require_matching_candle_id(
            series_id=series_id,
            aligned_time=int(aligned_time),
            factor_slices=factor_slices,
            draw_state=draw_state,
        )
        self._emit_frame_debug(
            event=debug_event,
            series_id=series_id,
            at_time=int(at_time),
            aligned_time=int(aligned_time),
            candle_id=candle_id,
        )
        return WorldStateV1(
            series_id=series_id,
            time=WorldTimeV1(at_time=int(at_time), aligned_time=int(aligned_time), candle_id=candle_id),
            factor_slices=factor_slices,
            draw_state=draw_state,
        )

    def read_frame_live(
        self,
        *,
        series_id: str,
        window_candles: int,
    ) -> WorldStateV1:
        store_head = self.store.head_time(series_id)
        if store_head is None:
            raise HTTPException(status_code=404, detail="no_data")
        overlay_head = self.overlay_store.head_time(series_id)
        if overlay_head is None:
            raise HTTPException(status_code=404, detail="no_overlay")
        aligned_base = min(int(store_head), int(overlay_head))
        aligned_time = self.store.floor_time(series_id, at_time=int(aligned_base))
        if aligned_time is None:
            raise HTTPException(status_code=404, detail="no_data")
        return self._build_world_state(
            series_id=series_id,
            at_time=int(store_head),
            aligned_time=int(aligned_time),
            window_candles=int(window_candles),
            debug_event="read.http.world_frame_live",
        )

    def read_frame_at_time(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
    ) -> WorldStateV1:
        aligned_time = self.store.floor_time(series_id, at_time=int(at_time))
        if aligned_time is None:
            raise HTTPException(status_code=404, detail="no_data")
        return self._build_world_state(
            series_id=series_id,
            at_time=int(at_time),
            aligned_time=int(aligned_time),
            window_candles=int(window_candles),
            debug_event="read.http.world_frame_at_time",
        )

    def poll_delta(
        self,
        *,
        series_id: str,
        after_id: int,
        limit: int,
        window_candles: int,
    ) -> WorldDeltaPollResponseV1:
        _ = int(limit)
        draw = self._read_draw_delta(
            series_id=series_id,
            cursor_version_id=int(after_id),
            window_candles=int(window_candles),
            at_time=None,
        )
        next_id = int(draw.next_cursor.version_id or 0)
        if draw.to_candle_id is None or draw.to_candle_time is None:
            return WorldDeltaPollResponseV1(series_id=series_id, records=[], next_cursor=WorldCursorV1(id=int(after_id)))

        if next_id <= int(after_id):
            return WorldDeltaPollResponseV1(series_id=series_id, records=[], next_cursor=WorldCursorV1(id=int(after_id)))

        rec = WorldDeltaRecordV1(
            id=int(next_id),
            series_id=series_id,
            to_candle_id=str(draw.to_candle_id),
            to_candle_time=int(draw.to_candle_time),
            draw_delta=draw,
            factor_slices=self._read_factor_slices(
                series_id=series_id,
                at_time=int(draw.to_candle_time),
                window_candles=int(window_candles),
            ),
        )
        if self._debug_enabled():
            self.debug_hub.emit(
                pipe="read",
                event="read.http.world_delta_poll",
                series_id=series_id,
                message="poll world delta",
                data={
                    "after_id": int(after_id),
                    "next_id": int(next_id),
                    "to_candle_time": int(draw.to_candle_time),
                    "has_record": True,
                },
            )
        return WorldDeltaPollResponseV1(series_id=series_id, records=[rec], next_cursor=WorldCursorV1(id=int(next_id)))
