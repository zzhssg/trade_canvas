from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass
class ShutdownState:
    shutting_down: bool = False


class ShutdownCancellationMiddleware(BaseHTTPMiddleware):
    """
    During process shutdown, uvicorn may cancel in-flight HTTP handlers.
    Convert those cancellations into a controlled 503 response to avoid noisy
    stack traces in shutdown logs.
    """

    def __init__(self, app, *, shutdown_state: ShutdownState) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._shutdown_state = shutdown_state

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        try:
            return await call_next(request)
        except asyncio.CancelledError:
            if bool(self._shutdown_state.shutting_down):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "server_shutting_down"},
                )
            raise
