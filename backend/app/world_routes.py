from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query

from .dependencies import WorldReadServiceDep
from .schemas import LimitQuery, WorldDeltaPollResponseV1, WorldStateV1

router = APIRouter()


@router.get("/api/frame/live", response_model=WorldStateV1)
def get_world_frame_live(
    series_id: str = Query(..., min_length=1),
    window_candles: LimitQuery = 2000,
    *,
    world_read_service: WorldReadServiceDep,
) -> WorldStateV1:
    """
    Unified world frame (live): latest aligned world state.
    v1 implementation is a projection of existing factor_slices + draw/delta.
    """
    return world_read_service.read_frame_live(
        series_id=series_id,
        window_candles=int(window_candles),
    )


@router.get("/api/frame/at_time", response_model=WorldStateV1)
def get_world_frame_at_time(
    series_id: str = Query(..., min_length=1),
    at_time: int = Query(..., ge=0),
    window_candles: LimitQuery = 2000,
    *,
    world_read_service: WorldReadServiceDep,
) -> WorldStateV1:
    """
    Unified world frame (replay point query): aligned world state at time t.
    """
    return world_read_service.read_frame_at_time(
        series_id=series_id,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )


@router.get("/api/delta/poll", response_model=WorldDeltaPollResponseV1)
def poll_world_delta(
    series_id: str = Query(..., min_length=1),
    after_id: int = Query(0, ge=0),
    limit: LimitQuery = 2000,
    window_candles: LimitQuery = 2000,
    *,
    world_read_service: WorldReadServiceDep,
) -> WorldDeltaPollResponseV1:
    """
    v1 world delta (live):
    - Uses draw/delta cursor as the minimal incremental source (compat projection).
    - Emits at most 1 record per poll (if cursor advances); otherwise returns empty records.
    """
    return world_read_service.poll_delta(
        series_id=series_id,
        after_id=int(after_id),
        limit=int(limit),
        window_candles=int(window_candles),
    )


def register_world_routes(app: FastAPI) -> None:
    app.include_router(router)
