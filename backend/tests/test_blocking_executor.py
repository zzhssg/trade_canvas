from __future__ import annotations

import asyncio
import unittest

from backend.app.blocking import run_blocking


class BlockingExecutorTests(unittest.TestCase):
    def test_run_blocking_returns_value(self) -> None:
        async def test_body() -> None:
            out = await run_blocking(lambda: 1 + 1)
            self.assertEqual(out, 2)

        asyncio.run(test_body())

