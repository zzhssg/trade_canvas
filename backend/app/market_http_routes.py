from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .market_flags import (
    debug_api_enabled,
    market_auto_tail_backfill_enabled,
    market_auto_tail_backfill_max_candles,
)
from .market_data import CatchupReadRequest
from .schemas import (
    GetCandlesResponse,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    SinceQuery,
)

router = APIRouter()


@router.get("/api/market/candles", response_model=GetCandlesResponse)
def get_market_candles(
    request: Request,
    series_id: str = Query(..., min_length=1),
    since: SinceQuery = None,
    limit: LimitQuery = 500,
) -> GetCandlesResponse:
    runtime = request.app.state.market_runtime
    if market_auto_tail_backfill_enabled():
        target = max(1, int(limit))
        target = min(int(target), int(market_auto_tail_backfill_max_candles(fallback=target)))
        runtime.backfill.ensure_tail_coverage(
            series_id=series_id,
            target_candles=int(target),
            to_time=None,
        )
    read_result = runtime.market_data.read_candles(CatchupReadRequest(series_id=series_id, since=since, limit=limit))
    candles = read_result.candles
    head_time = runtime.market_data.freshness(series_id=series_id).head_time
    if debug_api_enabled() and candles:
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
async def ingest_candle_closed(request: Request, req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
    runtime = request.app.state.market_runtime
    return await runtime.ingest.ingest_candle_closed(req)


@router.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
async def ingest_candle_forming(request: Request, req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
    runtime = request.app.state.market_runtime
    if not debug_api_enabled():
        raise HTTPException(status_code=404, detail="not_found")
    return await runtime.ingest.ingest_candle_forming(req)


def register_market_http_routes(app: FastAPI) -> None:
    app.include_router(router)
