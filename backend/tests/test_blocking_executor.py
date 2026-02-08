from __future__ import annotations

import asyncio
import unittest

from backend.app.blocking import _dispatch_future, run_blocking


class BlockingExecutorTests(unittest.TestCase):
    def test_run_blocking_returns_value(self) -> None:
        async def test_body() -> None:
            out = await run_blocking(lambda: 1 + 1)
            self.assertEqual(out, 2)

        asyncio.run(test_body())

    def test_dispatch_future_ignores_closed_loop(self) -> None:
        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        loop.close()
        _dispatch_future(loop=loop, fut=fut, value=42)
        self.assertFalse(fut.done())

    def test_dispatch_future_delivers_result(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            _dispatch_future(loop=loop, fut=fut, value=7)
            out = loop.run_until_complete(asyncio.wait_for(fut, timeout=0.2))
            self.assertEqual(out, 7)
        finally:
            loop.close()
