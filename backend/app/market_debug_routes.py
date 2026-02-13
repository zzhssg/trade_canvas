from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .dependencies import AppContainerDep, CandleStoreDep, IngestSupervisorDep, RuntimeFlagsDep, RuntimeMetricsDep
from .market_kline_health import analyze_series_health

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


@router.get("/api/market/debug/reconcile")
def get_market_reconcile_snapshot(
    series_id: str = Query(..., min_length=1),
    start_time: int | None = Query(None, ge=0),
    end_time: int | None = Query(None, ge=0),
    *,
    runtime_flags: RuntimeFlagsDep,
    container: AppContainerDep,
) -> dict:
    if not bool(runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    if not bool(runtime_flags.enable_pg_store):
        raise HTTPException(status_code=404, detail="not_found")
    service = container.data_reconcile_service
    try:
        snapshot = service.reconcile_series(
            series_id=series_id,
            start_time=start_time,
            end_time=end_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return snapshot.to_dict()


def register_market_debug_routes(app: FastAPI) -> None:
    app.include_router(router)
