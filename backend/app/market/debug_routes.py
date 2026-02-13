from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from ..dependencies import CandleStoreDep, IngestSupervisorDep, RuntimeFlagsDep, RuntimeMetricsDep
from .kline_health import analyze_series_health

router = APIRouter()


@router.get("/api/market/debug/ingest_state")
async def get_market_ingest_state(runtime_flags: RuntimeFlagsDep, supervisor: IngestSupervisorDep) -> dict:
    if not bool(runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    return await supervisor.debug_snapshot()


@router.get("/api/market/debug/series_health")
def get_market_series_health(
    series_id: str = Query(..., min_length=1),
    max_recent_gaps: int = Query(5, ge=1, le=50),
    recent_base_buckets: int = Query(8, ge=1, le=48),
    *,
    runtime_flags: RuntimeFlagsDep,
    store: CandleStoreDep,
) -> dict:
    if not bool(runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    return analyze_series_health(
        store=store,
        series_id=series_id,
        max_recent_gaps=int(max_recent_gaps),
        recent_base_buckets=int(recent_base_buckets),
    )


@router.get("/api/market/debug/metrics")
def get_market_runtime_metrics(runtime_flags: RuntimeFlagsDep, runtime_metrics: RuntimeMetricsDep) -> dict:
    if not bool(runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    if not bool(runtime_flags.enable_runtime_metrics):
        raise HTTPException(status_code=404, detail="not_found")
    return runtime_metrics.snapshot()


def register_market_debug_routes(app: FastAPI) -> None:
    app.include_router(router)
