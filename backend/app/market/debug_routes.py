from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from ..deps import ApiGatesDep, CandleStoreDep, IngestSupervisorDep, RuntimeMetricsDep
from .kline_health import analyze_series_health

router = APIRouter()


@router.get("/api/market/debug/ingest_state")
async def get_market_ingest_state(api_gates: ApiGatesDep, supervisor: IngestSupervisorDep) -> dict:
    if not api_gates.debug_api:
        raise HTTPException(status_code=404, detail="not_found")
    return await supervisor.debug_snapshot()


@router.get("/api/market/debug/series_health")
def get_market_series_health(
    series_id: str = Query(..., min_length=1),
    max_recent_gaps: int = Query(5, ge=1, le=50),
    recent_base_buckets: int = Query(8, ge=1, le=48),
    *,
    api_gates: ApiGatesDep,
    store: CandleStoreDep,
) -> dict:
    if not api_gates.debug_api:
        raise HTTPException(status_code=404, detail="not_found")
    return analyze_series_health(
        store=store,
        series_id=series_id,
        max_recent_gaps=int(max_recent_gaps),
        recent_base_buckets=int(recent_base_buckets),
    )


@router.get("/api/market/debug/metrics")
def get_market_runtime_metrics(api_gates: ApiGatesDep, runtime_metrics: RuntimeMetricsDep) -> dict:
    if not api_gates.debug_api:
        raise HTTPException(status_code=404, detail="not_found")
    if not api_gates.runtime_metrics:
        raise HTTPException(status_code=404, detail="not_found")
    return runtime_metrics.snapshot()


def register_market_debug_routes(app: FastAPI) -> None:
    app.include_router(router)
