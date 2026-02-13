from __future__ import annotations

import asyncio
import unittest

from backend.app.ws.hub import CandleHub


class _FakeWs:
    def __init__(self) -> None:
        self.closed: list[tuple[int, str]] = []

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed.append((int(code), str(reason or "")))


class WsHubCloseAllTests(unittest.TestCase):
    def test_close_all_clears_and_closes(self) -> None:
        async def test_body() -> None:
            hub = CandleHub()
            ws1 = _FakeWs()
            ws2 = _FakeWs()

            # Monkeypatch types: CandleHub stores by object identity; no FastAPI features needed here.
            await hub.subscribe(ws1, series_id="binance:spot:BTC/USDT:1m", since=0)  # type: ignore[arg-type]
            await hub.subscribe(ws2, series_id="binance:spot:BTC/USDT:1m", since=0)  # type: ignore[arg-type]

            await hub.close_all(code=1001, reason="server_shutdown")  # should not raise

            # Closing again should be idempotent and not close twice.
            await hub.close_all(code=1001, reason="server_shutdown")

            self.assertEqual(ws1.closed, [(1001, "server_shutdown")])
            self.assertEqual(ws2.closed, [(1001, "server_shutdown")])

        asyncio.run(test_body())


if __name__ == "__main__":
    unittest.main()

