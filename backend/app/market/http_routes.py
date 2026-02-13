from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from ..deps import (
    MarketIngestServiceDep,
    MarketLedgerWarmupServiceDep,
    MarketQueryServiceDep,
    RuntimeFlagsDep,
)
from ..core.schemas import (
    GetCandlesResponse,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    SinceQuery,
)
from ..core.service_errors import ServiceError, to_http_exception

router = APIRouter()


@router.get("/api/market/candles", response_model=GetCandlesResponse)
def get_market_candles(
    series_id: str = Query(..., min_length=1),
    since: SinceQuery = None,
    limit: LimitQuery = 500,
    *,
    warmup_service: MarketLedgerWarmupServiceDep,
    query_service: MarketQueryServiceDep,
) -> GetCandlesResponse:
    response = query_service.get_candles(
        series_id=series_id,
        since=None if since is None else int(since),
        limit=int(limit),
    )
    warmup_service.ensure_ledgers_warm(
        series_id=series_id,
        store_head_time=None if response.server_head_time is None else int(response.server_head_time),
    )
    return response


@router.post("/api/market/ingest/candle_closed", response_model=IngestCandleClosedResponse)
async def ingest_candle_closed(
    req: IngestCandleClosedRequest,
    ingest_service: MarketIngestServiceDep,
) -> IngestCandleClosedResponse:
    try:
        return await ingest_service.ingest_candle_closed(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
async def ingest_candle_forming(
    req: IngestCandleFormingRequest,
    runtime_flags: RuntimeFlagsDep,
    ingest_service: MarketIngestServiceDep,
) -> IngestCandleFormingResponse:
    if not bool(runtime_flags.enable_debug_api):
        raise HTTPException(status_code=404, detail="not_found")
    try:
        return await ingest_service.ingest_candle_forming(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_market_http_routes(app: FastAPI) -> None:
    app.include_router(router)
