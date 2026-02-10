from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .flags import resolve_env_bool


def _debug_enabled(ws: WebSocket) -> bool:
    return resolve_env_bool(
        "TRADE_CANVAS_ENABLE_DEBUG_API",
        fallback=bool(getattr(getattr(ws.app.state, "flags", None), "enable_debug_api", False)),
    )


async def handle_debug_ws(ws: WebSocket) -> None:
    if not _debug_enabled(ws):
        try:
            await ws.close(code=1008, reason="debug_api_disabled")
        except Exception:
            pass
        return

    await ws.accept()
    ws.app.state.debug_hub.register(ws, loop=asyncio.get_running_loop())
    try:
        await ws.send_json({"type": "debug_snapshot", "events": ws.app.state.debug_hub.snapshot()})
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "subscribe":
                await ws.send_json({"type": "debug_snapshot", "events": ws.app.state.debug_hub.snapshot()})
    except WebSocketDisconnect:
        pass
    finally:
        ws.app.state.debug_hub.unregister(ws)
        try:
            await ws.close(code=1001)
        except Exception:
            pass
