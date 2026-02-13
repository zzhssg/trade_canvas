from __future__ import annotations

import json
import time
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from starlette.responses import StreamingResponse

from ..dependencies import MarketForceLimiterDep, MarketListServiceDep
from ..schemas import TopMarketItem, TopMarketsLimitQuery, TopMarketsResponse

router = APIRouter()


@router.get("/api/market/top_markets", response_model=TopMarketsResponse)
def get_top_markets(
    request: Request,
    exchange: str = Query("binance", min_length=1),
    market: Literal["spot", "futures"] = Query(...),
    quote_asset: str = Query("USDT", min_length=1, max_length=12),
    limit: TopMarketsLimitQuery = 20,
    force: bool = False,
    *,
    force_limiter: MarketForceLimiterDep,
    market_list: MarketListServiceDep,
) -> TopMarketsResponse:
    if exchange != "binance":
        raise HTTPException(status_code=400, detail="unsupported exchange")
    if force:
        ip = request.client.host if request.client else "unknown"
        if not force_limiter.allow(key=f"{ip}:{market}"):
            raise HTTPException(status_code=429, detail="rate_limited")
    try:
        items, cached = market_list.get_top_markets(
            market=market,
            quote_asset=quote_asset,
            limit=limit,
            force_refresh=force,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream_error:{exc}") from exc

    return TopMarketsResponse(
        exchange="binance",
        market=market,
        quote_asset=quote_asset.upper(),
        limit=int(limit),
        generated_at_ms=int(time.time() * 1000),
        cached=bool(cached),
        items=[
            TopMarketItem(
                exchange=m.exchange,
                market=m.market,
                symbol=m.symbol,
                symbol_id=m.symbol_id,
                base_asset=m.base_asset,
                quote_asset=m.quote_asset,
                last_price=m.last_price,
                quote_volume=m.quote_volume,
                price_change_percent=m.price_change_percent,
            )
            for m in items
        ],
    )


@router.get("/api/market/top_markets/stream")
async def stream_top_markets(
    request: Request,
    exchange: str = Query("binance", min_length=1),
    market: Literal["spot", "futures"] = Query(...),
    quote_asset: str = Query("USDT", min_length=1, max_length=12),
    limit: TopMarketsLimitQuery = 20,
    interval_s: float = Query(2.0, ge=0.2, le=30.0),
    max_events: int = Query(0, ge=0, le=1000),
    *,
    market_list: MarketListServiceDep,
) -> StreamingResponse:
    if exchange != "binance":
        raise HTTPException(status_code=400, detail="unsupported exchange")

    async def make_payload() -> dict:
        import anyio
        import functools

        fn = functools.partial(
            market_list.get_top_markets,
            market=market,
            quote_asset=quote_asset,
            limit=limit,
            force_refresh=False,
        )
        items, cached = await anyio.to_thread.run_sync(fn)
        return {
            "exchange": "binance",
            "market": market,
            "quote_asset": quote_asset.upper(),
            "limit": int(limit),
            "generated_at_ms": int(time.time() * 1000),
            "cached": bool(cached),
            "items": [
                {
                    "exchange": m.exchange,
                    "market": m.market,
                    "symbol": m.symbol,
                    "symbol_id": m.symbol_id,
                    "base_asset": m.base_asset,
                    "quote_asset": m.quote_asset,
                    "last_price": m.last_price,
                    "quote_volume": m.quote_volume,
                    "price_change_percent": m.price_change_percent,
                }
                for m in items
            ],
        }

    async def event_stream():
        import anyio

        last_fingerprint: str | None = None
        emitted = 0
        while True:
            if await request.is_disconnected():
                return
            try:
                payload = await make_payload()
                fingerprint = json.dumps(
                    payload.get("items", []),
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if last_fingerprint != fingerprint:
                    last_fingerprint = fingerprint
                    data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
                    event_id = str(payload["generated_at_ms"])
                    yield f"id: {event_id}\nevent: top_markets\ndata: {data}\n\n".encode("utf-8")
                    emitted += 1
                    if max_events and emitted >= max_events:
                        return
            except Exception as exc:
                err = {"type": "error", "message": str(exc), "at_ms": int(time.time() * 1000)}
                data = json.dumps(err, separators=(",", ":"), sort_keys=True)
                yield f"event: error\ndata: {data}\n\n".encode("utf-8")
                emitted += 1
                if max_events and emitted >= max_events:
                    return

            yield f": ping {int(time.time())}\n\n".encode("utf-8")
            await anyio.sleep(float(interval_s))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def register_market_top_markets_routes(app: FastAPI) -> None:
    app.include_router(router)
