from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from .blocking import run_blocking
from .backtest_routes import register_backtest_routes
from .config import load_settings
from .debug_hub import DebugHub
from .dev_routes import register_dev_routes
from .factor_routes import register_factor_routes
from .factor_read_freshness import ensure_factor_fresh_for_read
from .market_ws_routes import handle_market_ws
from .overlay_package_routes import register_overlay_package_routes
from .replay_routes import register_replay_routes
from .world_routes import register_world_routes
from .ingest_supervisor import IngestSupervisor
from .schemas import (
    DrawDeltaV1,
    GetCandlesResponse,
    GetFactorSlicesResponseV1,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    SinceQuery,
    TopMarketsLimitQuery,
    TopMarketsResponse,
)
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .factor_orchestrator import FactorOrchestrator
from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .overlay_orchestrator import OverlayOrchestrator
from .overlay_store import OverlayStore
from .replay_package_service_v1 import ReplayPackageServiceV1
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .market_backfill import backfill_market_gap_best_effort
from .market_data import (
    CatchupReadRequest,
    DefaultMarketDataOrchestrator,
    HubWsDeliveryService,
    StoreBackfillService,
    StoreCandleReadService,
    StoreFreshnessService,
    WsMessageParser,
    WsSubscriptionCoordinator,
    build_derived_initial_backfill_handler,
    build_gap_backfill_handler,
)
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub
from .worktree_manager import WorktreeManager

_faulthandler_file: TextIO | None = None


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _maybe_enable_faulthandler() -> None:
    """
    Optional: allow dumping stack traces even when Ctrl+C appears stuck.

    Usage (when enabled): `kill -USR1 <pid>` to print all thread tracebacks to stderr.
    """
    if os.environ.get("TRADE_CANVAS_ENABLE_FAULTHANDLER") != "1":
        return
    try:
        import faulthandler
        import signal
        import sys

        file: TextIO = sys.stderr
        path_raw = (os.environ.get("TRADE_CANVAS_FAULTHANDLER_PATH") or "").strip()
        if path_raw:
            p = Path(path_raw).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            global _faulthandler_file
            _faulthandler_file = p.open("a", encoding="utf-8", buffering=1)
            file = _faulthandler_file

        faulthandler.enable(file=file)
        if hasattr(signal, "SIGUSR1"):
            faulthandler.register(signal.SIGUSR1, file=file, all_threads=True)
    except Exception:
        pass


def create_app() -> FastAPI:
    _maybe_enable_faulthandler()
    settings = load_settings()
    project_root = Path(__file__).resolve().parents[2]
    store = CandleStore(db_path=settings.db_path)
    factor_store = FactorStore(db_path=settings.db_path)
    factor_orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)
    factor_slices_service = FactorSlicesService(candle_store=store, factor_store=factor_store)
    overlay_store = OverlayStore(db_path=settings.db_path)
    overlay_orchestrator = OverlayOrchestrator(candle_store=store, factor_store=factor_store, overlay_store=overlay_store)
    replay_service = ReplayPackageServiceV1(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        factor_slices_service=factor_slices_service,
    )
    overlay_pkg_service = OverlayReplayPackageServiceV1(candle_store=store, overlay_store=overlay_store)
    debug_hub = DebugHub()
    factor_orchestrator.set_debug_hub(debug_hub)
    overlay_orchestrator.set_debug_hub(debug_hub)
    hub = CandleHub()
    reader_service = StoreCandleReadService(store=store)
    backfill_service = StoreBackfillService(
        store=store,
        gap_backfill_fn=lambda **kwargs: backfill_market_gap_best_effort(**kwargs),
    )
    hub.set_gap_backfill_handler(
        build_gap_backfill_handler(
            reader=reader_service,
            backfill=backfill_service,
            read_limit=settings.market_gap_backfill_read_limit,
        )
    )
    derived_initial_backfill = build_derived_initial_backfill_handler(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
    )
    market_data = DefaultMarketDataOrchestrator(
        reader=reader_service,
        freshness=StoreFreshnessService(
            store=store,
            fresh_window_candles=settings.market_fresh_window_candles,
            stale_window_candles=settings.market_stale_window_candles,
        ),
        ws_delivery=HubWsDeliveryService(hub=hub),
    )
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
    whitelist_ingest_enabled = os.environ.get("TRADE_CANVAS_ENABLE_WHITELIST_INGEST") == "1"

    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        whitelist_series_ids=whitelist.series_ids,
        ondemand_idle_ttl_s=idle_ttl_s,
        whitelist_ingest_enabled=whitelist_ingest_enabled,
    )
    ws_subscriptions = WsSubscriptionCoordinator(
        hub=hub,
        ondemand_subscribe=supervisor.subscribe,
        ondemand_unsubscribe=supervisor.unsubscribe,
    )
    ws_messages = WsMessageParser()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if whitelist_ingest_enabled:
            await supervisor.start_whitelist()

        if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
            await supervisor.start_reaper()

        try:
            yield
        finally:
            # Close websockets first so uvicorn doesn't wait on them.
            try:
                await hub.close_all()
            except Exception:
                pass
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
    app.state.market_data = market_data
    app.state.ws_messages = ws_messages
    app.state.ws_subscriptions = ws_subscriptions
    app.state.derived_initial_backfill = derived_initial_backfill
    app.state.market_ws_catchup_limit = int(settings.market_ws_catchup_limit)
    app.state.market_backfill = backfill_service
    app.state.factor_store = factor_store
    app.state.factor_orchestrator = factor_orchestrator
    app.state.factor_slices_service = factor_slices_service
    app.state.overlay_store = overlay_store
    app.state.overlay_orchestrator = overlay_orchestrator
    app.state.replay_service = replay_service
    app.state.overlay_pkg_service = overlay_pkg_service
    app.state.whitelist = whitelist
    app.state.market_list = market_list
    app.state.force_limiter = force_limiter
    app.state.ingest_supervisor = supervisor
    app.state.debug_hub = debug_hub
    app.state.settings = settings
    app.state.project_root = project_root

    # Initialize worktree manager
    worktree_manager = WorktreeManager(repo_root=project_root)
    app.state.worktree_manager = worktree_manager

    register_factor_routes(app)
    register_dev_routes(app)
    register_backtest_routes(app)
    register_replay_routes(app)
    register_world_routes(app)
    register_overlay_package_routes(app)

    def read_factor_slices(*, series_id: str, at_time: int, window_candles: int) -> GetFactorSlicesResponseV1:
        aligned = store.floor_time(series_id, at_time=int(at_time))
        _ = ensure_factor_fresh_for_read(
            factor_orchestrator=app.state.factor_orchestrator,
            series_id=series_id,
            up_to_time=aligned,
        )
        return app.state.factor_slices_service.get_slices(
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    app.state.read_factor_slices = read_factor_slices

    @app.get("/api/market/candles", response_model=GetCandlesResponse)
    def get_market_candles(
        series_id: str = Query(..., min_length=1),
        since: SinceQuery = None,
        limit: LimitQuery = 500,
    ) -> GetCandlesResponse:
        if _truthy_flag(os.environ.get("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL")):
            target = max(1, int(limit))
            max_target_raw = (os.environ.get("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES") or "").strip()
            if max_target_raw:
                try:
                    target = min(int(target), max(1, int(max_target_raw)))
                except ValueError:
                    pass
            app.state.market_backfill.ensure_tail_coverage(
                series_id=series_id,
                target_candles=int(target),
                to_time=None,
            )
        read_result = app.state.market_data.read_candles(
            CatchupReadRequest(series_id=series_id, since=since, limit=limit)
        )
        candles = read_result.candles
        head_time = app.state.market_data.freshness(series_id=series_id).head_time
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1" and candles:
            last_time = int(candles[-1].candle_time)
            app.state.debug_hub.emit(
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

    @app.post("/api/market/ingest/candle_closed", response_model=IngestCandleClosedResponse)
    async def ingest_candle_closed(req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
        # IMPORTANT: keep the asyncio event loop responsive.
        # SQLite writes and factor/overlay computation are sync and may take seconds for large bursts.
        t0 = time.perf_counter()
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_start",
                series_id=req.series_id,
                message="ingest candle_closed start",
                data={"candle_time": int(req.candle.candle_time)},
            )

        steps: list[dict] = []
        factor_rebuilt = {"value": False}

        def _persist_and_sidecars() -> None:
            t_step = time.perf_counter()
            store.upsert_closed(req.series_id, req.candle)
            steps.append(
                {
                    "name": "store.upsert_closed",
                    "ok": True,
                    "duration_ms": int((time.perf_counter() - t_step) * 1000),
                }
            )

            try:
                t_step = time.perf_counter()
                factor_result = app.state.factor_orchestrator.ingest_closed(
                    series_id=req.series_id, up_to_candle_time=req.candle.candle_time
                )
                factor_rebuilt["value"] = bool(getattr(factor_result, "rebuilt", False))
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
                if factor_rebuilt["value"]:
                    app.state.overlay_orchestrator.reset_series(series_id=req.series_id)
                app.state.overlay_orchestrator.ingest_closed(
                    series_id=req.series_id, up_to_candle_time=req.candle.candle_time
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
        await hub.publish_closed(series_id=req.series_id, candle=req.candle)
        if factor_rebuilt["value"]:
            await hub.publish_system(
                series_id=req.series_id,
                event="factor.rebuild",
                message="因子口径更新，已自动完成历史重算",
                data={"series_id": req.series_id},
            )

        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
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

    @app.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
    async def ingest_candle_forming(req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            raise HTTPException(status_code=404, detail="not_found")
        await hub.publish_forming(series_id=req.series_id, candle=req.candle)
        return IngestCandleFormingResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)

    @app.get("/api/draw/delta", response_model=DrawDeltaV1)
    def get_draw_delta(
        series_id: str = Query(..., min_length=1),
        cursor_version_id: int = Query(0, ge=0),
        window_candles: LimitQuery = 2000,
        at_time: int | None = Query(default=None, ge=0, description="Optional replay upper-bound (Unix seconds)"),
    ) -> DrawDeltaV1:
        """
        Unified draw delta (v1 base):
        - instruction_catalog_patch + active_ids (overlay instructions)
        - series_points (indicator line points; v0 returns empty for now)
        """
        from .schemas import DrawCursorV1, DrawDeltaV1, OverlayInstructionPatchItemV1

        store_head = store.head_time(series_id)
        overlay_head = app.state.overlay_store.head_time(series_id)

        if at_time is not None:
            aligned = store.floor_time(series_id, at_time=int(at_time))
            if aligned is None:
                return DrawDeltaV1(
                    series_id=series_id,
                    to_candle_id=None,
                    to_candle_time=None,
                    active_ids=[],
                    instruction_catalog_patch=[],
                    series_points={},
                    next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
                )
            # Replay/point-query semantics must be fail-safe: draw output cannot claim it is aligned to t
            # unless the overlay store has actually been built up to that aligned time.
            if overlay_head is None or int(overlay_head) < int(aligned):
                raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")
            to_time = int(aligned)
        else:
            # Live path should default to the latest closed candle.
            # Overlay lag is healed below (cursor=0 path) by deterministic rebuild checks.
            to_time = store_head if store_head is not None else overlay_head
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

        if int(cursor_version_id) == 0:
            _ = ensure_factor_fresh_for_read(
                factor_orchestrator=app.state.factor_orchestrator,
                series_id=series_id,
                up_to_time=int(to_time),
            )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        if int(cursor_version_id) == 0:
            expected_start = 0
            expected_has_zhongshu = False
            expected_zhongshu_ids: set[str] = set()
            try:
                slices = app.state.factor_slices_service.get_slices(
                    series_id=series_id,
                    at_time=int(to_time),
                    window_candles=int(window_candles),
                )
                anchor_snapshot = (slices.snapshots or {}).get("anchor")
                anchor_head = (anchor_snapshot.head if anchor_snapshot is not None else {}) or {}
                current_ref = anchor_head.get("current_anchor_ref") if isinstance(anchor_head, dict) else None
                if isinstance(current_ref, dict):
                    expected_start = int(current_ref.get("start_time") or 0)
                zhongshu_snapshot = (slices.snapshots or {}).get("zhongshu")
                if zhongshu_snapshot is not None:
                    zhongshu_history = (zhongshu_snapshot.history or {}) if isinstance(zhongshu_snapshot.history, dict) else {}
                    zhongshu_head = (zhongshu_snapshot.head or {}) if isinstance(zhongshu_snapshot.head, dict) else {}
                    dead_items = zhongshu_history.get("dead")
                    alive_items = zhongshu_head.get("alive")
                    if isinstance(dead_items, list):
                        for item in dead_items:
                            if not isinstance(item, dict):
                                continue
                            try:
                                start_time = int(item.get("start_time") or 0)
                                end_time = int(item.get("end_time") or 0)
                                zg = float(item.get("zg") or 0.0)
                                zd = float(item.get("zd") or 0.0)
                            except Exception:
                                continue
                            if start_time <= 0 or end_time <= 0:
                                continue
                            base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
                            expected_zhongshu_ids.add(f"{base_id}:top")
                            expected_zhongshu_ids.add(f"{base_id}:bottom")
                    if isinstance(alive_items, list) and alive_items:
                        expected_zhongshu_ids.add("zhongshu.alive:top")
                        expected_zhongshu_ids.add("zhongshu.alive:bottom")
                    expected_has_zhongshu = bool(
                        (isinstance(dead_items, list) and len(dead_items) > 0)
                        or (isinstance(alive_items, list) and len(alive_items) > 0)
                    )
            except Exception:
                expected_start = 0
                expected_has_zhongshu = False
                expected_zhongshu_ids = set()

            should_rebuild_overlay = False
            if expected_start > 0:
                current_def = next((d for d in latest_defs if d.kind == "polyline" and d.instruction_id == "anchor.current"), None)
                rendered_start = 0
                if current_def is not None:
                    pts = current_def.payload.get("points")
                    if isinstance(pts, list) and pts:
                        first = pts[0]
                        if isinstance(first, dict):
                            try:
                                rendered_start = int(first.get("time") or 0)
                            except Exception:
                                rendered_start = 0
                if int(rendered_start) != int(expected_start):
                    should_rebuild_overlay = True

            rendered_has_zhongshu = any(str(d.instruction_id).startswith("zhongshu.") for d in latest_defs)
            if bool(rendered_has_zhongshu) != bool(expected_has_zhongshu):
                should_rebuild_overlay = True
            rendered_zhongshu_ids = {str(d.instruction_id) for d in latest_defs if str(d.instruction_id).startswith("zhongshu.")}
            if rendered_zhongshu_ids != expected_zhongshu_ids:
                should_rebuild_overlay = True

            if should_rebuild_overlay:
                app.state.overlay_orchestrator.reset_series(series_id=series_id)
                app.state.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_time))
                latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(
                    series_id=series_id, up_to_time=int(to_time)
                )
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
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1" and (patch or int(next_cursor.version_id) > int(cursor_version_id)):
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.draw_delta",
                series_id=series_id,
                message="get draw delta",
                data={
                    "cursor_version_id": int(cursor_version_id),
                    "next_version_id": int(next_cursor.version_id),
                    "to_time": None if to_time is None else int(to_time),
                    "patch_len": int(len(patch)),
                    "active_len": int(len(active_ids)),
                    "at_time": None if at_time is None else int(at_time),
                },
            )
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=int(to_time),
            active_ids=active_ids,
            instruction_catalog_patch=patch,
            series_points={},
            next_cursor=next_cursor,
        )

    app.state.read_draw_delta = get_draw_delta

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

    @app.websocket("/ws/market")
    async def ws_market(ws: WebSocket) -> None:
        await handle_market_ws(ws)

    @app.websocket("/ws/debug")
    async def ws_debug(ws: WebSocket) -> None:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            try:
                await ws.close(code=1008, reason="debug_api_disabled")
            except Exception:
                pass
            return

        await ws.accept()
        app.state.debug_hub.register(ws, loop=asyncio.get_running_loop())
        try:
            await ws.send_json({"type": "debug_snapshot", "events": app.state.debug_hub.snapshot()})
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "subscribe":
                    await ws.send_json({"type": "debug_snapshot", "events": app.state.debug_hub.snapshot()})
        except WebSocketDisconnect:
            pass
        finally:
            app.state.debug_hub.unregister(ws)
            try:
                await ws.close(code=1001)
            except Exception:
                pass

    return app


app = create_app()
