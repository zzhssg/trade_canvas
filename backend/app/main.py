from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .backtest_routes import register_backtest_routes
from .config import load_settings
from .debug_hub import DebugHub
from .debug_routes import handle_debug_ws
from .dev_routes import register_dev_routes
from .draw_routes import register_draw_routes
from .factor_routes import register_factor_routes
from .factor_read_freshness import read_factor_slices_with_freshness
from .market_http_routes import register_market_http_routes
from .market_meta_routes import register_market_meta_routes
from .market_runtime import MarketRuntime
from .market_ws_routes import handle_market_ws
from .overlay_package_routes import register_overlay_package_routes
from .replay_routes import register_replay_routes
from .world_routes import register_world_routes
from .ingest_supervisor import IngestSupervisor
from .schemas import GetFactorSlicesResponseV1
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
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub
from .worktree_manager import WorktreeManager

_faulthandler_file: TextIO | None = None


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
    market_runtime = MarketRuntime(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        hub=hub,
        reader=reader_service,
        backfill=backfill_service,
        market_data=market_data,
        whitelist=whitelist,
        market_list=market_list,
        force_limiter=force_limiter,
        supervisor=supervisor,
        ws_subscriptions=ws_subscriptions,
        ws_messages=ws_messages,
        derived_initial_backfill=derived_initial_backfill,
        ws_catchup_limit=int(settings.market_ws_catchup_limit),
    )

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
    app.state.market_runtime = market_runtime
    app.state.factor_store = factor_store
    app.state.factor_orchestrator = factor_orchestrator
    app.state.factor_slices_service = factor_slices_service
    app.state.overlay_store = overlay_store
    app.state.overlay_orchestrator = overlay_orchestrator
    app.state.replay_service = replay_service
    app.state.overlay_pkg_service = overlay_pkg_service
    app.state.debug_hub = debug_hub
    app.state.settings = settings
    app.state.project_root = project_root

    # Initialize worktree manager
    worktree_manager = WorktreeManager(repo_root=project_root)
    app.state.worktree_manager = worktree_manager

    register_factor_routes(app)
    register_draw_routes(app)
    register_dev_routes(app)
    register_backtest_routes(app)
    register_replay_routes(app)
    register_world_routes(app)
    register_overlay_package_routes(app)
    register_market_meta_routes(app)
    register_market_http_routes(app)

    def read_factor_slices(*, series_id: str, at_time: int, window_candles: int) -> GetFactorSlicesResponseV1:
        return read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=app.state.factor_orchestrator,
            factor_slices_service=app.state.factor_slices_service,
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    app.state.read_factor_slices = read_factor_slices

    @app.websocket("/ws/market")
    async def ws_market(ws: WebSocket) -> None:
        await handle_market_ws(ws)

    @app.websocket("/ws/debug")
    async def ws_debug(ws: WebSocket) -> None:
        await handle_debug_ws(ws)

    return app


app = create_app()
