from __future__ import annotations

import asyncio
import unittest

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from backend.app.lifecycle.shutdown_cancellation_middleware import ShutdownCancellationMiddleware, ShutdownState


def _build_request(app: FastAPI) -> Request:
    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "app": app,
    }
    return Request(scope, _receive)


class ShutdownCancellationMiddlewareTests(unittest.TestCase):
    def test_returns_503_when_cancelled_during_shutdown(self) -> None:
        app = FastAPI()
        shutdown_state = ShutdownState(shutting_down=True)
        middleware = ShutdownCancellationMiddleware(app, shutdown_state=shutdown_state)
        request = _build_request(app)

        async def _call_next(_: Request) -> Response:
            raise asyncio.CancelledError()

        async def _run() -> Response:
            return await middleware.dispatch(request, _call_next)

        response = asyncio.run(_run())
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)

    def test_reraises_cancelled_error_when_not_shutting_down(self) -> None:
        app = FastAPI()
        shutdown_state = ShutdownState(shutting_down=False)
        middleware = ShutdownCancellationMiddleware(app, shutdown_state=shutdown_state)
        request = _build_request(app)

        async def _call_next(_: Request) -> Response:
            raise asyncio.CancelledError()

        async def _run() -> None:
            with self.assertRaises(asyncio.CancelledError):
                await middleware.dispatch(request, _call_next)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
