from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query, Request

from .schemas import GetFactorSlicesResponseV1, LimitQuery

router = APIRouter()


def _ensure_factor_fresh_for_read(*, request: Request, series_id: str, up_to_time: int | None) -> bool:
    if up_to_time is None:
        return False
    to_time = int(up_to_time)
    if to_time <= 0:
        return False
    result = request.app.state.factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=to_time)
    return bool(getattr(result, "rebuilt", False))


@router.get("/api/factor/slices", response_model=GetFactorSlicesResponseV1)
def get_factor_slices(
    request: Request,
    series_id: str = Query(..., min_length=1),
    at_time: int = Query(..., ge=0),
    window_candles: LimitQuery = 2000,
) -> GetFactorSlicesResponseV1:
    """
    Read-side factor slices at aligned time t.
    Returns history/head snapshots produced by the current modular factor pipeline.
    """
    aligned = request.app.state.store.floor_time(series_id, at_time=int(at_time))
    _ = _ensure_factor_fresh_for_read(request=request, series_id=series_id, up_to_time=aligned)
    return request.app.state.factor_slices_service.get_slices(
        series_id=series_id,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )


def register_factor_routes(app: FastAPI) -> None:
    app.include_router(router)
