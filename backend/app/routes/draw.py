from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query

from ..deps import DrawReadServiceDep
from ..core.schemas import DrawDeltaV1, LimitQuery
from ..core.service_errors import ServiceError, to_http_exception

router = APIRouter()


@router.get("/api/draw/delta", response_model=DrawDeltaV1)
def get_draw_delta(
    series_id: str = Query(..., min_length=1),
    cursor_version_id: int = Query(0, ge=0),
    window_candles: LimitQuery = 2000,
    at_time: int | None = Query(default=None, ge=0, description="Optional replay upper-bound (Unix seconds)"),
    *,
    draw_read_service: DrawReadServiceDep,
) -> DrawDeltaV1:
    try:
        return draw_read_service.read_delta(
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            window_candles=int(window_candles),
            at_time=None if at_time is None else int(at_time),
        )
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_draw_routes(app: FastAPI) -> None:
    app.include_router(router)
