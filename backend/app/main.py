from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .backtest_routes import register_backtest_routes
from .config import load_settings
from .container import build_app_container
from .debug_routes import handle_debug_ws
from .dev_routes import register_dev_routes
from .draw_routes import register_draw_routes
from .factor_routes import register_factor_routes
from .market_http_routes import register_market_http_routes
from .market_meta_routes import register_market_meta_routes
from .market_ws_routes import handle_market_ws
from .overlay_package_routes import register_overlay_package_routes
from .replay_routes import register_replay_routes
from .startup_kline_sync import run_startup_kline_sync_for_runtime
from .world_routes import register_world_routes

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
    container = build_app_container(settings=settings, project_root=project_root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if bool(container.runtime_flags.enable_startup_kline_sync):
            await run_startup_kline_sync_for_runtime(
                runtime=container.market_runtime,
                enabled=bool(container.runtime_flags.enable_startup_kline_sync),
                target_candles=int(container.runtime_flags.startup_kline_sync_target_candles),
            )

        if container.whitelist_ingest_enabled:
            await container.supervisor.start_whitelist()

        if bool(container.flags.enable_ondemand_ingest):
            await container.supervisor.start_reaper()

        try:
            yield
        finally:
            try:
                await container.hub.close_all()
            except Exception:
                pass
            await container.supervisor.close()

    app = FastAPI(title="trade_canvas API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.container = container

    register_factor_routes(app)
    register_draw_routes(app)
    register_dev_routes(app)
    register_backtest_routes(app)
    register_replay_routes(app)
    register_world_routes(app)
    register_overlay_package_routes(app)
    register_market_meta_routes(app)
    register_market_http_routes(app)

    @app.websocket("/ws/market")
    async def ws_market(ws: WebSocket) -> None:
        await handle_market_ws(ws, runtime=container.market_runtime)

    @app.websocket("/ws/debug")
    async def ws_debug(ws: WebSocket) -> None:
        await handle_debug_ws(
            ws,
            debug_hub=container.debug_hub,
            flags=container.flags,
        )

    return app


app = create_app()
