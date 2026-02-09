from __future__ import annotations

import os
from typing import Callable

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .schemas import (
    DrawDeltaV1,
    GetFactorSlicesResponseV1,
    LimitQuery,
    WorldCursorV1,
    WorldDeltaPollResponseV1,
    WorldDeltaRecordV1,
    WorldStateV1,
    WorldTimeV1,
)

router = APIRouter()


def _read_factor_slices(
    request: Request,
    *,
    series_id: str,
    at_time: int,
    window_candles: int,
) -> GetFactorSlicesResponseV1:
    reader = request.app.state.read_factor_slices
    if not callable(reader):
        raise HTTPException(status_code=500, detail="factor_slices_reader_not_ready")
    return reader(series_id=series_id, at_time=int(at_time), window_candles=int(window_candles))


def _read_draw_delta(
    request: Request,
    *,
    series_id: str,
    cursor_version_id: int,
    window_candles: int,
    at_time: int | None,
) -> DrawDeltaV1:
    reader: Callable[..., DrawDeltaV1] = request.app.state.read_draw_delta
    if not callable(reader):
        raise HTTPException(status_code=500, detail="draw_delta_reader_not_ready")
    return reader(
        series_id=series_id,
        cursor_version_id=int(cursor_version_id),
        window_candles=int(window_candles),
        at_time=None if at_time is None else int(at_time),
    )


@router.get("/api/frame/live", response_model=WorldStateV1)
def get_world_frame_live(
    request: Request,
    series_id: str = Query(..., min_length=1),
    window_candles: LimitQuery = 2000,
) -> WorldStateV1:
    """
    Unified world frame (live): latest aligned world state.
    v1 implementation is a projection of existing factor_slices + draw/delta.
    """
    store = request.app.state.store
    store_head = store.head_time(series_id)
    if store_head is None:
        raise HTTPException(status_code=404, detail="no_data")
    overlay_head = request.app.state.overlay_store.head_time(series_id)
    if overlay_head is None:
        raise HTTPException(status_code=404, detail="no_overlay")
    aligned_base = min(int(store_head), int(overlay_head))
    aligned = store.floor_time(series_id, at_time=int(aligned_base))
    if aligned is None:
        raise HTTPException(status_code=404, detail="no_data")

    factor_slices = _read_factor_slices(
        request,
        series_id=series_id,
        at_time=int(aligned),
        window_candles=int(window_candles),
    )
    draw_state = _read_draw_delta(
        request,
        series_id=series_id,
        cursor_version_id=0,
        window_candles=int(window_candles),
        at_time=int(aligned),
    )
    candle_id = f"{series_id}:{int(aligned)}"
    if factor_slices.candle_id != candle_id or draw_state.to_candle_id != candle_id:
        raise HTTPException(status_code=409, detail="ledger_out_of_sync")
    if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
        request.app.state.debug_hub.emit(
            pipe="read",
            event="read.http.world_frame_live",
            series_id=series_id,
            message="get world frame live",
            data={"at_time": int(store_head), "aligned_time": int(aligned), "candle_id": str(candle_id)},
        )
    return WorldStateV1(
        series_id=series_id,
        time=WorldTimeV1(at_time=int(store_head), aligned_time=int(aligned), candle_id=candle_id),
        factor_slices=factor_slices,
        draw_state=draw_state,
    )


@router.get("/api/frame/at_time", response_model=WorldStateV1)
def get_world_frame_at_time(
    request: Request,
    series_id: str = Query(..., min_length=1),
    at_time: int = Query(..., ge=0),
    window_candles: LimitQuery = 2000,
) -> WorldStateV1:
    """
    Unified world frame (replay point query): aligned world state at time t.
    """
    store = request.app.state.store
    aligned = store.floor_time(series_id, at_time=int(at_time))
    if aligned is None:
        raise HTTPException(status_code=404, detail="no_data")

    factor_slices = _read_factor_slices(
        request,
        series_id=series_id,
        at_time=int(aligned),
        window_candles=int(window_candles),
    )
    draw_state = _read_draw_delta(
        request,
        series_id=series_id,
        cursor_version_id=0,
        window_candles=int(window_candles),
        at_time=int(aligned),
    )
    candle_id = f"{series_id}:{int(aligned)}"
    if factor_slices.candle_id != candle_id or draw_state.to_candle_id != candle_id:
        raise HTTPException(status_code=409, detail="ledger_out_of_sync")
    if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
        request.app.state.debug_hub.emit(
            pipe="read",
            event="read.http.world_frame_live",
            series_id=series_id,
            message="get world frame live",
            data={"at_time": int(at_time), "aligned_time": int(aligned), "candle_id": str(candle_id)},
        )
    return WorldStateV1(
        series_id=series_id,
        time=WorldTimeV1(at_time=int(at_time), aligned_time=int(aligned), candle_id=candle_id),
        factor_slices=factor_slices,
        draw_state=draw_state,
    )


@router.get("/api/delta/poll", response_model=WorldDeltaPollResponseV1)
def poll_world_delta(
    request: Request,
    series_id: str = Query(..., min_length=1),
    after_id: int = Query(0, ge=0),
    limit: LimitQuery = 2000,
    window_candles: LimitQuery = 2000,
) -> WorldDeltaPollResponseV1:
    """
    v1 world delta (live):
    - Uses draw/delta cursor as the minimal incremental source (compat projection).
    - Emits at most 1 record per poll (if cursor advances); otherwise returns empty records.
    """
    _ = int(limit)
    draw = _read_draw_delta(
        request,
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
        factor_slices=_read_factor_slices(
            request,
            series_id=series_id,
            at_time=int(draw.to_candle_time),
            window_candles=int(window_candles),
        ),
    )
    if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
        request.app.state.debug_hub.emit(
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


def register_world_routes(app: FastAPI) -> None:
    app.include_router(router)
