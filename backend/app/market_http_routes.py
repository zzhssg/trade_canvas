from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .dependencies import MarketRuntimeDep
from .market_data import CatchupReadRequest
from .market_ingest_service import MarketIngestService
from .schemas import (
    GetCandlesResponse,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    SinceQuery,
)
from .service_errors import ServiceError, to_http_exception

router = APIRouter()


def _require_market_ingest_service(runtime: MarketRuntimeDep) -> MarketIngestService:
    ingest_service = runtime.ingest
    if ingest_service is None:
        raise HTTPException(status_code=500, detail="market_ingest_not_ready")
    return ingest_service


@router.get("/api/market/candles", response_model=GetCandlesResponse)
def get_market_candles(
    series_id: str = Query(..., min_length=1),
    since: SinceQuery = None,
    limit: LimitQuery = 500,
    *,
    runtime: MarketRuntimeDep,
) -> GetCandlesResponse:
    runtime_flags = runtime.runtime_flags
    if bool(runtime_flags.enable_market_auto_tail_backfill):
        target = max(1, int(limit))
        max_candles = runtime_flags.market_auto_tail_backfill_max_candles
        if max_candles is not None:
            target = min(int(target), max(1, int(max_candles)))
        runtime.backfill.ensure_tail_coverage(
            series_id=series_id,
            target_candles=int(target),
            to_time=None,
        )
    read_result = runtime.market_data.read_candles(CatchupReadRequest(series_id=series_id, since=since, limit=limit))
    candles = read_result.candles
    head_time = runtime.market_data.freshness(series_id=series_id).head_time
    if bool(runtime_flags.enable_debug_api) and candles:
        last_time = int(candles[-1].candle_time)
        runtime.debug_hub.emit(
            pipe="read",
            event="read.http.market_candles",
            series_id=series_id,
            message="get market candles",
            data={
                "since": None if since is None else int(since),
                "limit": int(limit),
                "count": int(len(candles)),
                "last_time": int(last_time),
                "server_head_time": None if head_time is None else int(head_time),
            },
        )
    return GetCandlesResponse(series_id=series_id, server_head_time=head_time, candles=candles)


@router.post("/api/market/ingest/candle_closed", response_model=IngestCandleClosedResponse)
async def ingest_candle_closed(
    req: IngestCandleClosedRequest,
    runtime: MarketRuntimeDep,
) -> IngestCandleClosedResponse:
    ingest_service = _require_market_ingest_service(runtime)
    try:
        return await ingest_service.ingest_candle_closed(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
async def ingest_candle_forming(
    req: IngestCandleFormingRequest,
    runtime: MarketRuntimeDep,
) -> IngestCandleFormingResponse:
    if not bool(runtime.runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    ingest_service = _require_market_ingest_service(runtime)
    try:
        return await ingest_service.ingest_candle_forming(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_market_http_routes(app: FastAPI) -> None:
    app.include_router(router)
