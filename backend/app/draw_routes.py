from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .read_models import DrawReadService
from .schemas import DrawDeltaV1, LimitQuery

router = APIRouter()


def _get_draw_read_service(app: FastAPI) -> DrawReadService:
    service = getattr(app.state, "draw_read_service", None)
    if service is not None:
        return service

    factor_read_service = getattr(app.state, "factor_read_service", None)
    if factor_read_service is None:
        raise HTTPException(status_code=500, detail="factor_read_service_not_ready")

    service = DrawReadService(
        store=app.state.store,
        overlay_store=app.state.overlay_store,
        overlay_orchestrator=app.state.overlay_orchestrator,
        factor_read_service=factor_read_service,
        debug_hub=app.state.debug_hub,
        debug_api_fallback=bool(getattr(getattr(app.state, "flags", None), "enable_debug_api", False)),
    )
    app.state.draw_read_service = service
    return service


def _compute_draw_delta(
    *,
    app: FastAPI,
    series_id: str,
    cursor_version_id: int,
    window_candles: int,
    at_time: int | None,
) -> DrawDeltaV1:
    return _get_draw_read_service(app).read_delta(
        series_id=series_id,
        cursor_version_id=int(cursor_version_id),
        window_candles=int(window_candles),
        at_time=None if at_time is None else int(at_time),
    )


@router.get("/api/draw/delta", response_model=DrawDeltaV1)
def get_draw_delta(
    request: Request,
    series_id: str = Query(..., min_length=1),
    cursor_version_id: int = Query(0, ge=0),
    window_candles: LimitQuery = 2000,
    at_time: int | None = Query(default=None, ge=0, description="Optional replay upper-bound (Unix seconds)"),
) -> DrawDeltaV1:
    return _compute_draw_delta(
        app=request.app,
        series_id=series_id,
        cursor_version_id=int(cursor_version_id),
        window_candles=int(window_candles),
        at_time=None if at_time is None else int(at_time),
    )


def register_draw_routes(app: FastAPI) -> None:
    app.include_router(router)

    def _read_draw_delta(*, series_id: str, cursor_version_id: int, window_candles: int, at_time: int | None) -> DrawDeltaV1:
        return _compute_draw_delta(
            app=app,
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            window_candles=int(window_candles),
            at_time=None if at_time is None else int(at_time),
        )

    app.state.read_draw_delta = _read_draw_delta
