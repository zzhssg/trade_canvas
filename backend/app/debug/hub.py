from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass(frozen=True)
class DebugEvent:
    ts_ms: int
    source: str  # "backend" | "frontend" (backend only here)
    pipe: str  # "read" | "write"
    event: str
    series_id: str | None
    level: str  # "info" | "warn" | "error"
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ts_ms": int(self.ts_ms),
            "source": str(self.source),
            "pipe": str(self.pipe),
            "event": str(self.event),
            "series_id": self.series_id,
            "level": str(self.level),
            "message": str(self.message),
        }
        if self.data is not None:
            out["data"] = self.data
        return out


class DebugHub:
    """
    Thread-safe debug event hub.

    - Can be called from worker threads (run_blocking) via emit().
    - Keeps a ring buffer so that clients can see recent history after connecting.
    - Broadcasts to WS clients via the main asyncio loop.
    """

    def __init__(self, *, max_events: int = 2000) -> None:
        self._lock = threading.Lock()
        self._events: deque[DebugEvent] = deque(maxlen=int(max_events))
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def register(self, ws: WebSocket, *, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._clients.add(ws)
            self._loop = loop

    def unregister(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in list(self._events)]

    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        e = DebugEvent(
            ts_ms=int(time.time() * 1000),
            source="backend",
            pipe=str(pipe),
            event=str(event),
            series_id=str(series_id) if series_id is not None else None,
            level=str(level),
            message=str(message),
            data=data,
        )

        with self._lock:
            self._events.append(e)
            loop = self._loop
            targets = list(self._clients)

        if loop is None or not targets:
            return

        payload = {"type": "debug_event", "event": e.to_dict()}

        def schedule() -> None:
            asyncio.create_task(self._broadcast(payload=payload, targets=targets))

        try:
            loop.call_soon_threadsafe(schedule)
        except Exception:
            pass

    async def _broadcast(self, *, payload: dict[str, Any], targets: list[WebSocket]) -> None:
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                self.unregister(ws)

