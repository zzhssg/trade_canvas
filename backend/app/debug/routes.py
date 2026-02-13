from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .hub import DebugHub
from ..runtime.flags import RuntimeFlags


def _debug_enabled(*, flags: RuntimeFlags) -> bool:
    return bool(flags.enable_debug_api)


async def handle_debug_ws(
    ws: WebSocket,
    *,
    debug_hub: DebugHub,
    flags: RuntimeFlags,
) -> None:
    if not _debug_enabled(flags=flags):
        try:
            await ws.close(code=1008, reason="debug_api_disabled")
        except Exception:
            pass
        return

    await ws.accept()
    debug_hub.register(ws, loop=asyncio.get_running_loop())
    try:
        await ws.send_json({"type": "debug_snapshot", "events": debug_hub.snapshot()})
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "subscribe":
                await ws.send_json({"type": "debug_snapshot", "events": debug_hub.snapshot()})
    except WebSocketDisconnect:
        pass
    finally:
        debug_hub.unregister(ws)
        try:
            await ws.close(code=1001)
        except Exception:
            pass
