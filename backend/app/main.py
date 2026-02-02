from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from .config import load_settings
from .freqtrade_config import build_backtest_config, load_json, write_temp_config
from .freqtrade_runner import list_strategies, parse_strategy_list, run_backtest, validate_strategy_name
from .ingest_supervisor import IngestSupervisor
from .schemas import (
    BacktestRunRequest,
    BacktestRunResponse,
    GetCandlesResponse,
    GetFactorSlicesResponseV1,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    DrawDeltaV1,
    OverlayDeltaV1,
    PlotDeltaV1,
    SinceQuery,
    StrategyListResponse,
    TopMarketsLimitQuery,
    TopMarketsResponse,
)
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .factor_orchestrator import FactorOrchestrator
from .factor_store import FactorStore
from .overlay_orchestrator import OverlayOrchestrator
from .overlay_store import OverlayStore
from .plot_orchestrator import PlotOrchestrator
from .plot_store import PlotStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = load_settings()
    store = CandleStore(db_path=settings.db_path)
    plot_store = PlotStore(db_path=settings.db_path)
    plot_orchestrator = PlotOrchestrator(candle_store=store, plot_store=plot_store)
    factor_store = FactorStore(db_path=settings.db_path)
    factor_orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)
    overlay_store = OverlayStore(db_path=settings.db_path)
    overlay_orchestrator = OverlayOrchestrator(candle_store=store, factor_store=factor_store, overlay_store=overlay_store)
    hub = CandleHub()
    whitelist = load_market_whitelist(settings.whitelist_path)
    market_list = BinanceMarketListService()
    force_limiter = MinIntervalLimiter(min_interval_s=2.0)

    idle_ttl_s = 60
    idle_ttl_raw = os.environ.get("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", "").strip()
    if idle_ttl_raw:
        try:
            idle_ttl_s = max(1, int(idle_ttl_raw))
        except ValueError:
            idle_ttl_s = 60

    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        plot_orchestrator=plot_orchestrator,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        whitelist_series_ids=whitelist.series_ids,
        ondemand_idle_ttl_s=idle_ttl_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if os.environ.get("TRADE_CANVAS_ENABLE_WHITELIST_INGEST") == "1":
            await supervisor.start_whitelist()

        if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
            await supervisor.start_reaper()

        try:
            yield
        finally:
            await supervisor.close()

    app = FastAPI(title="trade_canvas API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.store = store
    app.state.hub = hub
    app.state.plot_store = plot_store
    app.state.plot_orchestrator = plot_orchestrator
    app.state.factor_store = factor_store
    app.state.factor_orchestrator = factor_orchestrator
    app.state.overlay_store = overlay_store
    app.state.overlay_orchestrator = overlay_orchestrator
    app.state.whitelist = whitelist
    app.state.market_list = market_list
    app.state.force_limiter = force_limiter
    app.state.ingest_supervisor = supervisor

    @app.get("/api/market/candles", response_model=GetCandlesResponse)
    def get_market_candles(
        series_id: str = Query(..., min_length=1),
        since: SinceQuery = None,
        limit: LimitQuery = 500,
    ) -> GetCandlesResponse:
        candles = store.get_closed(series_id, since=since, limit=limit)
        head_time = store.head_time(series_id)
        return GetCandlesResponse(series_id=series_id, server_head_time=head_time, candles=candles)

    @app.post("/api/market/ingest/candle_closed", response_model=IngestCandleClosedResponse)
    async def ingest_candle_closed(req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
        store.upsert_closed(req.series_id, req.candle)
        try:
            app.state.plot_orchestrator.ingest_closed(series_id=req.series_id, up_to_candle_time=req.candle.candle_time)
        except Exception:
            # Plot ingest must never break market ingest (best-effort).
            pass
        try:
            app.state.factor_orchestrator.ingest_closed(series_id=req.series_id, up_to_candle_time=req.candle.candle_time)
        except Exception:
            # Factor ingest must never break market ingest (best-effort).
            pass
        try:
            app.state.overlay_orchestrator.ingest_closed(series_id=req.series_id, up_to_candle_time=req.candle.candle_time)
        except Exception:
            # Overlay ingest must never break market ingest (best-effort).
            pass
        await hub.publish_closed(series_id=req.series_id, candle=req.candle)
        return IngestCandleClosedResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)

    @app.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
    async def ingest_candle_forming(req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            raise HTTPException(status_code=404, detail="not_found")
        await hub.publish_forming(series_id=req.series_id, candle=req.candle)
        return IngestCandleFormingResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)

    @app.get("/api/plot/delta", response_model=PlotDeltaV1)
    def get_plot_delta(
        series_id: str = Query(..., min_length=1),
        cursor_candle_time: SinceQuery = None,
        cursor_overlay_event_id: int | None = Query(None, ge=0),
        window_candles: LimitQuery = 2000,
    ) -> PlotDeltaV1:
        from .schemas import OverlayEventV1, PlotCursorV1

        store_head = store.head_time(series_id)
        plot_head = app.state.plot_store.head_time(series_id)
        to_time = plot_head if plot_head is not None else store_head
        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        events: list[OverlayEventV1] = []
        if to_time is not None:
            tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
            cutoff = max(0, int(to_time) - int(window_candles) * int(tf_s))

            if cursor_overlay_event_id is not None:
                rows = app.state.plot_store.get_overlay_events_after_id(
                    series_id=series_id, after_id=int(cursor_overlay_event_id)
                )
            else:
                since_time = cutoff
                if cursor_candle_time is not None:
                    since_time = max(int(cursor_candle_time), cutoff)
                rows = app.state.plot_store.get_overlay_events_since_candle_time(
                    series_id=series_id,
                    since_candle_time=int(since_time),
                )

            events = [
                OverlayEventV1(
                    id=r.id,
                    kind=r.kind,
                    candle_id=r.candle_id,
                    candle_time=r.candle_time,
                    payload=r.payload,
                )
                for r in rows
            ]

        last_event_id = max([e.id for e in events], default=cursor_overlay_event_id)
        next_cursor = PlotCursorV1(candle_time=to_time, overlay_event_id=last_event_id if last_event_id is not None else None)

        return PlotDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=to_time,
            lines={},
            overlay_events=events,
            next_cursor=next_cursor,
        )

    @app.get("/api/overlay/delta", response_model=OverlayDeltaV1)
    def get_overlay_delta(
        series_id: str = Query(..., min_length=1),
        cursor_version_id: int = Query(0, ge=0),
        window_candles: LimitQuery = 2000,
    ):
        from .schemas import OverlayCursorV1, OverlayDeltaV1, OverlayInstructionPatchItemV1

        store_head = store.head_time(series_id)
        overlay_head = app.state.overlay_store.head_time(series_id)
        to_time = overlay_head if overlay_head is not None else store_head
        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        if to_time is None:
            return OverlayDeltaV1(
                series_id=series_id,
                to_candle_id=None,
                to_candle_time=None,
                active_ids=[],
                instruction_catalog_patch=[],
                next_cursor=OverlayCursorV1(version_id=int(cursor_version_id)),
            )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        active_ids: list[str] = []
        for d in latest_defs:
            if d.kind == "marker":
                t = d.payload.get("time")
                try:
                    pivot_time = int(t)
                except Exception:
                    continue
                if pivot_time < cutoff_time or pivot_time > int(to_time):
                    continue
                active_ids.append(str(d.instruction_id))
            elif d.kind == "polyline":
                pts = d.payload.get("points")
                if not isinstance(pts, list) or not pts:
                    continue
                # Active when any point overlaps tail window.
                ok = False
                for p in pts:
                    if not isinstance(p, dict):
                        continue
                    tt = p.get("time")
                    try:
                        pt = int(tt)
                    except Exception:
                        continue
                    if cutoff_time <= pt <= int(to_time):
                        ok = True
                        break
                if ok:
                    active_ids.append(str(d.instruction_id))

        patch_rows = app.state.overlay_store.get_patch_after_version(
            series_id=series_id,
            after_version_id=int(cursor_version_id),
            up_to_time=int(to_time),
        )
        patch = [
            OverlayInstructionPatchItemV1(
                version_id=r.version_id,
                instruction_id=r.instruction_id,
                kind=r.kind,
                visible_time=r.visible_time,
                definition=r.payload,
            )
            for r in patch_rows
        ]
        next_cursor = OverlayCursorV1(version_id=int(app.state.overlay_store.last_version_id(series_id)))

        active_ids.sort()
        return OverlayDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=int(to_time),
            active_ids=active_ids,
            instruction_catalog_patch=patch,
            next_cursor=next_cursor,
        )

    @app.get("/api/draw/delta", response_model=DrawDeltaV1)
    def get_draw_delta(
        series_id: str = Query(..., min_length=1),
        cursor_version_id: int = Query(0, ge=0),
        window_candles: LimitQuery = 2000,
    ) -> DrawDeltaV1:
        """
        Unified draw delta (v1 base):
        - instruction_catalog_patch + active_ids (overlay instructions)
        - series_points (indicator line points; v0 returns empty for now)
        """
        from .schemas import DrawCursorV1, DrawDeltaV1, OverlayInstructionPatchItemV1

        store_head = store.head_time(series_id)
        overlay_head = app.state.overlay_store.head_time(series_id)
        to_time = overlay_head if overlay_head is not None else store_head
        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        if to_time is None:
            return DrawDeltaV1(
                series_id=series_id,
                to_candle_id=None,
                to_candle_time=None,
                active_ids=[],
                instruction_catalog_patch=[],
                series_points={},
                next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
            )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        active_ids: list[str] = []
        for d in latest_defs:
            if d.kind == "marker":
                t = d.payload.get("time")
                try:
                    pivot_time = int(t)
                except Exception:
                    continue
                if pivot_time < cutoff_time or pivot_time > int(to_time):
                    continue
                active_ids.append(str(d.instruction_id))
            elif d.kind == "polyline":
                pts = d.payload.get("points")
                if not isinstance(pts, list) or not pts:
                    continue
                ok = False
                for p in pts:
                    if not isinstance(p, dict):
                        continue
                    tt = p.get("time")
                    try:
                        pt = int(tt)
                    except Exception:
                        continue
                    if cutoff_time <= pt <= int(to_time):
                        ok = True
                        break
                if ok:
                    active_ids.append(str(d.instruction_id))

        patch_rows = app.state.overlay_store.get_patch_after_version(
            series_id=series_id,
            after_version_id=int(cursor_version_id),
            up_to_time=int(to_time),
        )
        patch = [
            OverlayInstructionPatchItemV1(
                version_id=r.version_id,
                instruction_id=r.instruction_id,
                kind=r.kind,
                visible_time=r.visible_time,
                definition=r.payload,
            )
            for r in patch_rows
        ]
        next_cursor = DrawCursorV1(version_id=int(app.state.overlay_store.last_version_id(series_id)), point_time=None)

        active_ids.sort()
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=int(to_time),
            active_ids=active_ids,
            instruction_catalog_patch=patch,
            series_points={},
            next_cursor=next_cursor,
        )

    @app.get("/api/factor/slices", response_model=GetFactorSlicesResponseV1)
    def get_factor_slices(
        series_id: str = Query(..., min_length=1),
        at_time: int = Query(..., ge=0),
        window_candles: LimitQuery = 2000,
    ) -> GetFactorSlicesResponseV1:
        """
        v0 debug endpoint to inspect which factor snapshots are available at time t.

        Note: v0 supports:
        - pivot: history.major from factor events, head.minor computed on the fly
        - pen: history.confirmed from factor events
        """
        from .schemas import FactorMetaV1, FactorSliceV1

        aligned = store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=None)

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(aligned) - int(window_candles) * int(tf_s))

        factor_rows = app.state.factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(start_time),
            end_candle_time=int(aligned),
        )

        piv_major: list[dict] = []
        piv_minor: list[dict] = []
        pen_confirmed: list[dict] = []
        zhongshu_dead: list[dict] = []

        def is_visible(payload: dict, *, at_time: int) -> bool:
            vt = payload.get("visible_time")
            if vt is None:
                return True
            try:
                return int(vt) <= int(at_time)
            except Exception:
                return True

        for r in factor_rows:
            if r.factor_name == "pivot" and r.kind == "pivot.major":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    piv_major.append(payload)
            elif r.factor_name == "pivot" and r.kind == "pivot.minor":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    piv_minor.append(payload)
            elif r.factor_name == "pen" and r.kind == "pen.confirmed":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    pen_confirmed.append(payload)
            elif r.factor_name == "zhongshu" and r.kind == "zhongshu.dead":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    zhongshu_dead.append(payload)

        piv_major.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("pivot_time", 0))))
        pen_confirmed.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("start_time", 0))))

        snapshots: dict[str, FactorSliceV1] = {}
        factors: list[str] = []
        candle_id = f"{series_id}:{int(aligned)}"

        if piv_major:
            factors.append("pivot")
            snapshots["pivot"] = FactorSliceV1(
                history={"major": piv_major, "minor": piv_minor},
                head={},
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="pivot",
                ),
            )

        if pen_confirmed:
            factors.append("pen")
            snapshots["pen"] = FactorSliceV1(
                history={"confirmed": pen_confirmed},
                head={},
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="pen",
                ),
            )

        if zhongshu_dead:
            factors.append("zhongshu")
            snapshots["zhongshu"] = FactorSliceV1(
                history={"dead": zhongshu_dead},
                head={},
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="zhongshu",
                ),
            )

        return GetFactorSlicesResponseV1(
            series_id=series_id,
            at_time=int(aligned),
            candle_id=candle_id,
            factors=factors,
            snapshots=snapshots,
        )

    @app.get("/api/market/whitelist")
    def get_market_whitelist() -> dict[str, list[str]]:
        return {"series_ids": list(whitelist.series_ids)}

    @app.get("/api/market/debug/ingest_state")
    async def get_market_ingest_state() -> dict:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            raise HTTPException(status_code=404, detail="not_found")
        return await app.state.ingest_supervisor.debug_snapshot()

    @app.get("/api/market/top_markets", response_model=TopMarketsResponse)
    def get_top_markets(
        request: Request,
        exchange: str = Query("binance", min_length=1),
        market: str = Query(..., pattern="^(spot|futures)$"),
        quote_asset: str = Query("USDT", min_length=1, max_length=12),
        limit: TopMarketsLimitQuery = 20,
        force: bool = False,
    ) -> TopMarketsResponse:
        if exchange != "binance":
            raise HTTPException(status_code=400, detail="unsupported exchange")
        if force:
            ip = request.client.host if request.client else "unknown"
            if not app.state.force_limiter.allow(key=f"{ip}:{market}"):
                raise HTTPException(status_code=429, detail="rate_limited")
        try:
            items, cached = app.state.market_list.get_top_markets(
                market=market, quote_asset=quote_asset, limit=limit, force_refresh=force
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"upstream_error:{e}") from e

        return TopMarketsResponse(
            exchange="binance",
            market=market,
            quote_asset=quote_asset.upper(),
            limit=int(limit),
            generated_at_ms=int(time.time() * 1000),
            cached=bool(cached),
            items=[
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
        )

    @app.get("/api/market/top_markets/stream")
    async def stream_top_markets(
        request: Request,
        exchange: str = Query("binance", min_length=1),
        market: str = Query(..., pattern="^(spot|futures)$"),
        quote_asset: str = Query("USDT", min_length=1, max_length=12),
        limit: TopMarketsLimitQuery = 20,
        interval_s: float = Query(2.0, ge=0.2, le=30.0),
        max_events: int = Query(0, ge=0, le=1000),
    ) -> StreamingResponse:
        if exchange != "binance":
            raise HTTPException(status_code=400, detail="unsupported exchange")

        async def make_payload() -> dict:
            import anyio
            import functools

            fn = functools.partial(
                app.state.market_list.get_top_markets,
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
            import json
            import anyio

            last_fingerprint: str | None = None
            emitted = 0

            while True:
                if await request.is_disconnected():
                    return

                try:
                    payload = await make_payload()
                    # Fingerprint ignores timestamps so we can suppress duplicates.
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
                except Exception as e:
                    err = {"type": "error", "message": str(e), "at_ms": int(time.time() * 1000)}
                    data = json.dumps(err, separators=(",", ":"), sort_keys=True)
                    yield f"event: error\ndata: {data}\n\n".encode("utf-8")
                    emitted += 1
                    if max_events and emitted >= max_events:
                        return

                # Keep-alive comment (some proxies close idle streams).
                yield f": ping {int(time.time())}\n\n".encode("utf-8")
                await anyio.sleep(float(interval_s))

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/backtest/strategies", response_model=StrategyListResponse)
    def get_backtest_strategies(recursive: bool = True) -> StrategyListResponse:
        if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
            return StrategyListResponse(strategies=["DemoStrategy"])

        res = list_strategies(
            freqtrade_bin=settings.freqtrade_bin,
            userdir=settings.freqtrade_userdir,
            cwd=settings.freqtrade_root,
            recursive=recursive,
            strategy_path=settings.freqtrade_strategy_path,
        )
        strategies = parse_strategy_list(res.stdout)
        if not res.ok and not strategies:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "freqtrade list-strategies failed",
                    "exit_code": res.exit_code,
                    "stderr": res.stderr,
                },
            )
        return StrategyListResponse(strategies=strategies)

    @app.post("/api/backtest/run", response_model=BacktestRunResponse)
    def run_backtest_job(payload: BacktestRunRequest) -> BacktestRunResponse:
        if not validate_strategy_name(payload.strategy_name):
            raise HTTPException(status_code=400, detail="Invalid strategy_name")

        if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
            if payload.strategy_name != "DemoStrategy":
                raise HTTPException(status_code=404, detail="Strategy not found in userdir")
            pair = payload.pair
            command = [
                settings.freqtrade_bin,
                "backtesting",
                "--strategy",
                payload.strategy_name,
                "--timeframe",
                payload.timeframe,
                "--pairs",
                pair,
            ]
            if payload.timerange:
                command.extend(["--timerange", payload.timerange])
            stdout = "\n".join(
                [
                    "TRADE_CANVAS MOCK BACKTEST",
                    f"strategy={payload.strategy_name}",
                    f"pair={pair}",
                    f"timeframe={payload.timeframe}",
                    f"timerange={payload.timerange or ''}",
                    "result=ok",
                ]
            )
            return BacktestRunResponse(
                ok=True,
                exit_code=0,
                duration_ms=1,
                command=command,
                stdout=stdout,
                stderr="",
            )

        if settings.freqtrade_config_path is None:
            raise HTTPException(
                status_code=500,
                detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.",
            )
        if not settings.freqtrade_config_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Freqtrade config not found: {settings.freqtrade_config_path}",
            )
        if not settings.freqtrade_root.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Freqtrade root not found: {settings.freqtrade_root}",
            )
        if settings.freqtrade_userdir is not None and not settings.freqtrade_userdir.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Freqtrade userdir not found: {settings.freqtrade_userdir}",
            )

        strategies_res = list_strategies(
            freqtrade_bin=settings.freqtrade_bin,
            userdir=settings.freqtrade_userdir,
            cwd=settings.freqtrade_root,
            recursive=True,
            strategy_path=settings.freqtrade_strategy_path,
        )
        strategies = set(parse_strategy_list(strategies_res.stdout))
        if payload.strategy_name not in strategies:
            raise HTTPException(status_code=404, detail="Strategy not found in userdir")

        pair = payload.pair
        base_cfg: dict = {}
        try:
            base_cfg = load_json(settings.freqtrade_config_path)
            trading_mode = str(base_cfg.get("trading_mode") or "")
            stake_currency = str(base_cfg.get("stake_currency") or "USDT")
            if trading_mode == "futures" and "/" in pair and ":" not in pair:
                pair = f"{pair}:{stake_currency}"
        except Exception:
            pass

        if not base_cfg:
            base_cfg = load_json(settings.freqtrade_config_path)
        bt_cfg = build_backtest_config(base_cfg, pair=pair, timeframe=payload.timeframe)
        tmp_config = write_temp_config(bt_cfg, root_dir=settings.freqtrade_root)
        try:
            res = run_backtest(
                freqtrade_bin=settings.freqtrade_bin,
                userdir=settings.freqtrade_userdir,
                cwd=settings.freqtrade_root,
                config_path=tmp_config,
                strategy_name=payload.strategy_name,
                pair=pair,
                timeframe=payload.timeframe,
                timerange=payload.timerange,
                strategy_path=settings.freqtrade_strategy_path,
            )
        finally:
            try:
                tmp_config.unlink(missing_ok=True)
            except Exception:
                pass

        # Requirement: print freqtrade backtest results.
        # Keep stdout/stderr separated but both are printed for convenience.
        if res.stdout.strip():
            logger.info("freqtrade backtesting stdout:\n%s", res.stdout.rstrip("\n"))
        if res.stderr.strip():
            logger.info("freqtrade backtesting stderr:\n%s", res.stderr.rstrip("\n"))

        return BacktestRunResponse(
            ok=res.ok,
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
            command=res.command,
            stdout=res.stdout,
            stderr=res.stderr,
        )

    @app.websocket("/ws/market")
    async def ws_market(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_json()
                msg_type = msg.get("type")
                if msg_type == "subscribe":
                    series_id = msg.get("series_id")
                    if not isinstance(series_id, str) or not series_id:
                        await ws.send_json({"type": "error", "code": "bad_request", "message": "missing series_id"})
                        continue
                    since = msg.get("since")
                    if since is not None and not isinstance(since, int):
                        await ws.send_json({"type": "error", "code": "bad_request", "message": "invalid since"})
                        continue

                    if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
                        ok = await ws.app.state.ingest_supervisor.subscribe(series_id)
                        if not ok:
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "code": "capacity",
                                    "message": "ondemand_ingest_capacity",
                                    "series_id": series_id,
                                }
                            )

                    await hub.subscribe(ws, series_id=series_id, since=since)

                    catchup = store.get_closed(series_id, since=since, limit=5000)
                    for candle in catchup:
                        await ws.send_json(
                            {"type": "candle_closed", "series_id": series_id, "candle": candle.model_dump()}
                        )
                        await hub.set_last_sent(ws, series_id=series_id, candle_time=candle.candle_time)

                elif msg_type == "unsubscribe":
                    series_id = msg.get("series_id")
                    if isinstance(series_id, str) and series_id:
                        if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
                            await ws.app.state.ingest_supervisor.unsubscribe(series_id)
                        await hub.unsubscribe(ws, series_id=series_id)
                else:
                    await ws.send_json({"type": "error", "code": "bad_request", "message": "unknown message type"})
        except WebSocketDisconnect:
            await hub.remove_ws(ws)

    return app


app = create_app()
