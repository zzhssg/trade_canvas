from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel

from ..deps import CandleStoreDep, FactorReadServiceDep, FactorStoreDep, OverlayStoreDep
from .catalog import build_factor_catalog_response
from ..core.schemas import GetFactorCatalogResponseV1, GetFactorSlicesResponseV1, LimitQuery
from ..core.series_id import parse_series_id
from ..core.service_errors import ServiceError, to_http_exception
from ..core.timeframe import timeframe_to_seconds

router = APIRouter()

HealthTone = Literal["green", "yellow", "red", "gray"]


class FactorDrawHealthResponseV1(BaseModel):
    series_id: str
    timeframe_seconds: int
    store_head_time: int | None
    factor_head_time: int | None
    overlay_head_time: int | None
    factor_delay_seconds: int | None
    factor_delay_candles: int | None
    overlay_delay_seconds: int | None
    overlay_delay_candles: int | None
    max_delay_seconds: int | None
    max_delay_candles: int | None
    status: HealthTone
    status_reason: str


def _compute_delay(
    *,
    target_head_time: int | None,
    component_head_time: int | None,
    timeframe_seconds: int,
) -> tuple[int | None, int | None]:
    if target_head_time is None or component_head_time is None:
        return None, None
    missing_seconds = max(0, int(target_head_time) - int(component_head_time))
    if missing_seconds <= 0:
        return 0, 0
    tf = max(1, int(timeframe_seconds))
    missing_candles = max(1, int(math.ceil(float(missing_seconds) / float(tf))))
    return int(missing_seconds), int(missing_candles)


def _resolve_status(
    *,
    store_head: int | None,
    factor_head: int | None,
    overlay_head: int | None,
    max_delay_candles: int | None,
) -> tuple[HealthTone, str]:
    if store_head is None:
        return "gray", "no_store_head"
    if factor_head is None and overlay_head is None:
        return "red", "missing_factor_overlay_head"
    if factor_head is None:
        return "red", "missing_factor_head"
    if overlay_head is None:
        return "red", "missing_overlay_head"
    lag_candles = int(max_delay_candles or 0)
    if lag_candles <= 0:
        return "green", "up_to_date"
    if lag_candles <= 1:
        return "yellow", "lagging_one_candle"
    return "red", "lagging_many_candles"


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
    try:
        return factor_read_service.read_slices(
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/factor/health", response_model=FactorDrawHealthResponseV1)
def get_factor_draw_health(
    series_id: str = Query(..., min_length=1),
    *,
    store: CandleStoreDep,
    factor_store: FactorStoreDep,
    overlay_store: OverlayStoreDep,
) -> FactorDrawHealthResponseV1:
    try:
        parsed = parse_series_id(series_id)
        timeframe_seconds = int(timeframe_to_seconds(parsed.timeframe))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store_head = store.head_time(series_id)
    factor_head = factor_store.head_time(series_id)
    overlay_head = overlay_store.head_time(series_id)
    factor_delay_seconds, factor_delay_candles = _compute_delay(
        target_head_time=store_head,
        component_head_time=factor_head,
        timeframe_seconds=timeframe_seconds,
    )
    overlay_delay_seconds, overlay_delay_candles = _compute_delay(
        target_head_time=store_head,
        component_head_time=overlay_head,
        timeframe_seconds=timeframe_seconds,
    )

    delay_seconds_candidates = [value for value in (factor_delay_seconds, overlay_delay_seconds) if value is not None]
    delay_candles_candidates = [value for value in (factor_delay_candles, overlay_delay_candles) if value is not None]
    max_delay_seconds = max(delay_seconds_candidates) if delay_seconds_candidates else None
    max_delay_candles = max(delay_candles_candidates) if delay_candles_candidates else None
    status, status_reason = _resolve_status(
        store_head=store_head,
        factor_head=factor_head,
        overlay_head=overlay_head,
        max_delay_candles=max_delay_candles,
    )

    return FactorDrawHealthResponseV1(
        series_id=series_id,
        timeframe_seconds=timeframe_seconds,
        store_head_time=None if store_head is None else int(store_head),
        factor_head_time=None if factor_head is None else int(factor_head),
        overlay_head_time=None if overlay_head is None else int(overlay_head),
        factor_delay_seconds=None if factor_delay_seconds is None else int(factor_delay_seconds),
        factor_delay_candles=None if factor_delay_candles is None else int(factor_delay_candles),
        overlay_delay_seconds=None if overlay_delay_seconds is None else int(overlay_delay_seconds),
        overlay_delay_candles=None if overlay_delay_candles is None else int(overlay_delay_candles),
        max_delay_seconds=None if max_delay_seconds is None else int(max_delay_seconds),
        max_delay_candles=None if max_delay_candles is None else int(max_delay_candles),
        status=status,
        status_reason=status_reason,
    )


def register_factor_routes(app: FastAPI) -> None:
    app.include_router(router)
