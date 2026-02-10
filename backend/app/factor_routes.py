from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query

from .dependencies import FactorReadServiceDep
from .factor_catalog import build_factor_catalog_response
from .schemas import GetFactorCatalogResponseV1, GetFactorSlicesResponseV1, LimitQuery

router = APIRouter()


@router.get("/api/factor/catalog", response_model=GetFactorCatalogResponseV1)
def get_factor_catalog() -> GetFactorCatalogResponseV1:
    return build_factor_catalog_response()


@router.get("/api/factor/slices", response_model=GetFactorSlicesResponseV1)
def get_factor_slices(
    series_id: str = Query(..., min_length=1),
    at_time: int = Query(..., ge=0),
    window_candles: LimitQuery = 2000,
    *,
    factor_read_service: FactorReadServiceDep,
) -> GetFactorSlicesResponseV1:
    """
    Read-side factor slices at aligned time t.
    Returns history/head snapshots produced by the current modular factor pipeline.
    """
    return factor_read_service.read_slices(
        series_id=series_id,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )


def register_factor_routes(app: FastAPI) -> None:
    app.include_router(router)
