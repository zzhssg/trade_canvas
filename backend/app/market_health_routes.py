from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .dependencies import MarketRuntimeDep
from .market_health_service import build_market_health_snapshot
from .schemas import MarketBackfillStatusResponse, MarketHealthResponse

router = APIRouter()


@router.get("/api/market/whitelist")
def get_market_whitelist(runtime: MarketRuntimeDep) -> dict[str, list[str]]:
    whitelist = runtime.whitelist
    return {"series_ids": list(whitelist.series_ids)}


@router.get("/api/market/health", response_model=MarketHealthResponse)
def get_market_health(
    series_id: str = Query(..., min_length=1),
    now_time: int | None = Query(None, ge=0),
    *,
    runtime: MarketRuntimeDep,
) -> MarketHealthResponse:
    runtime_flags = runtime.runtime_flags
    if not (bool(runtime_flags.enable_kline_health_v2) or bool(runtime_flags.enable_debug_api)):
        raise HTTPException(status_code=404, detail="not_found")
    try:
        snapshot = build_market_health_snapshot(
            runtime=runtime,
            series_id=series_id,
            now_time=now_time,
            backfill_recent_seconds=int(runtime_flags.kline_health_backfill_recent_seconds),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MarketHealthResponse(
        series_id=snapshot.series_id,
        timeframe_seconds=snapshot.timeframe_seconds,
        now_time=snapshot.now_time,
        expected_latest_closed_time=snapshot.expected_latest_closed_time,
        head_time=snapshot.head_time,
        lag_seconds=snapshot.lag_seconds,
        missing_seconds=snapshot.missing_seconds,
        missing_candles=snapshot.missing_candles,
        status=snapshot.status,
        status_reason=snapshot.status_reason,
        backfill=MarketBackfillStatusResponse(
            state=snapshot.backfill.state,
            progress_pct=snapshot.backfill.progress_pct,
            started_at=snapshot.backfill.started_at,
            updated_at=snapshot.backfill.updated_at,
            reason=snapshot.backfill.reason,
            note=snapshot.backfill.note,
            error=snapshot.backfill.error,
            recent=snapshot.backfill.recent,
            start_missing_seconds=snapshot.backfill.start_missing_seconds,
            start_missing_candles=snapshot.backfill.start_missing_candles,
            current_missing_seconds=snapshot.backfill.current_missing_seconds,
            current_missing_candles=snapshot.backfill.current_missing_candles,
        ),
    )


def register_market_health_routes(app: FastAPI) -> None:
    app.include_router(router)
