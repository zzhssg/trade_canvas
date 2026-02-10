from __future__ import annotations

import os
import time

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .blocking import run_blocking
from .flags import resolve_env_bool
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
    debug_api_enabled = resolve_env_bool(
        "TRADE_CANVAS_ENABLE_DEBUG_API",
        fallback=bool(runtime.flags.enable_debug_api),
    )
    auto_tail_enabled = resolve_env_bool(
        "TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL",
        fallback=runtime.flags.enable_market_auto_tail_backfill,
    )
    if auto_tail_enabled:
        target = max(1, int(limit))
        max_target = runtime.flags.market_auto_tail_backfill_max_candles
        max_target_raw = (os.environ.get("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES") or "").strip()
        if max_target_raw:
            try:
                parsed = int(max_target_raw)
                if parsed > 0:
                    max_target = parsed
            except ValueError:
                pass
        if max_target is not None:
            target = min(int(target), max(1, int(max_target)))
        runtime.backfill.ensure_tail_coverage(
            series_id=series_id,
            target_candles=int(target),
            to_time=None,
        )
    read_result = runtime.market_data.read_candles(CatchupReadRequest(series_id=series_id, since=since, limit=limit))
    candles = read_result.candles
    head_time = runtime.market_data.freshness(series_id=series_id).head_time
    if debug_api_enabled and candles:
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
    debug_api_enabled = resolve_env_bool(
        "TRADE_CANVAS_ENABLE_DEBUG_API",
        fallback=bool(runtime.flags.enable_debug_api),
    )
    t0 = time.perf_counter()
    if debug_api_enabled:
        runtime.debug_hub.emit(
            pipe="write",
            event="write.http.ingest_candle_closed_start",
            series_id=req.series_id,
            message="ingest candle_closed start",
            data={"candle_time": int(req.candle.candle_time)},
        )

    steps: list[dict] = []

    if runtime.flags.enable_ingest_pipeline_v2:
        pipeline_result = await runtime.ingest_pipeline.run(
            batches={req.series_id: [req.candle]},
            publish=True,
        )
        steps.extend(
            {
                "name": str(step.name),
                "ok": bool(step.ok),
                "duration_ms": int(step.duration_ms),
                "error": step.error,
            }
            for step in pipeline_result.steps
        )
    else:
        factor_rebuilt_holder = {"value": False}

        def _persist_and_sidecars() -> None:
            t_step = time.perf_counter()
            runtime.store.upsert_closed(req.series_id, req.candle)
            steps.append(
                {
                    "name": "store.upsert_closed",
                    "ok": True,
                    "duration_ms": int((time.perf_counter() - t_step) * 1000),
                }
            )

            try:
                t_step = time.perf_counter()
                factor_result = runtime.factor_orchestrator.ingest_closed(
                    series_id=req.series_id,
                    up_to_candle_time=req.candle.candle_time,
                )
                factor_rebuilt_holder["value"] = bool(getattr(factor_result, "rebuilt", False))
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

            try:
                t_step = time.perf_counter()
                if factor_rebuilt_holder["value"]:
                    runtime.overlay_orchestrator.reset_series(series_id=req.series_id)
                runtime.overlay_orchestrator.ingest_closed(
                    series_id=req.series_id,
                    up_to_candle_time=req.candle.candle_time,
                )
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

        await run_blocking(_persist_and_sidecars)
        await runtime.hub.publish_closed(series_id=req.series_id, candle=req.candle)
        if factor_rebuilt_holder["value"]:
            await runtime.hub.publish_system(
                series_id=req.series_id,
                event="factor.rebuild",
                message="因子口径更新，已自动完成历史重算",
                data={"series_id": req.series_id},
            )

    if debug_api_enabled:
        runtime.debug_hub.emit(
            pipe="write",
            event="write.http.ingest_candle_closed_done",
            series_id=req.series_id,
            message="ingest candle_closed done",
            data={
                "candle_time": int(req.candle.candle_time),
                "steps": list(steps),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            },
        )

    return IngestCandleClosedResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)


@router.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
async def ingest_candle_forming(request: Request, req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
    runtime = request.app.state.market_runtime
    debug_api_enabled = resolve_env_bool(
        "TRADE_CANVAS_ENABLE_DEBUG_API",
        fallback=bool(runtime.flags.enable_debug_api),
    )
    if not debug_api_enabled:
        raise HTTPException(status_code=404, detail="not_found")
    await runtime.hub.publish_forming(series_id=req.series_id, candle=req.candle)
    return IngestCandleFormingResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)


def register_market_http_routes(app: FastAPI) -> None:
    app.include_router(router)
