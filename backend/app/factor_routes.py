from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .factor_catalog import build_factor_catalog_response
from .schemas import GetFactorCatalogResponseV1, GetFactorSlicesResponseV1, LimitQuery

router = APIRouter()


@router.get("/api/factor/catalog", response_model=GetFactorCatalogResponseV1)
def get_factor_catalog() -> GetFactorCatalogResponseV1:
    return build_factor_catalog_response()


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
    reader = getattr(request.app.state, "read_factor_slices", None)
    if callable(reader):
        return reader(
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    service = getattr(request.app.state, "factor_read_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="factor_read_service_not_ready")

    return service.read_slices(
        series_id=series_id,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )


def register_factor_routes(app: FastAPI) -> None:
    app.include_router(router)
