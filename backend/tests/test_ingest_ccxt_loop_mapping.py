from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.ingest_ccxt import WhitelistIngestSettings, run_whitelist_ingest_loop
from backend.app.store import CandleStore
from backend.app.ws_hub import CandleHub


class IngestCcxtLoopMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)

    def test_futures_series_id_maps_to_ccxt_symbol(self) -> None:
        async def test_body() -> None:
            store = CandleStore(db_path=self.db_path)
            hub = CandleHub()
            stop = asyncio.Event()
            fetched = asyncio.Event()
            seen: dict[str, object] = {}

            async def fake_fetch_ohlcv(exchange, symbol: str, timeframe: str, since_ms: int | None, limit: int):
                seen["symbol"] = symbol
                seen["timeframe"] = timeframe
                fetched.set()
                # Yield control to the event loop so other tasks/timeouts can run.
                await asyncio.sleep(0)
                # Return 1 closed candle well in the past.
                return [[9_000_000, 1, 2, 0.5, 1.5, 10]]  # ms

            with (
                patch("backend.app.ingest_ccxt._make_exchange_client", return_value=object()),
                patch("backend.app.ingest_ccxt._fetch_ohlcv", side_effect=fake_fetch_ohlcv),
                patch("backend.app.ingest_ccxt.time.time", return_value=10_000),
            ):
                settings = WhitelistIngestSettings(grace_window_s=0, poll_interval_s=0.01, batch_limit=10)

                task = asyncio.create_task(
                    run_whitelist_ingest_loop(
                        series_id="binance:futures:BTC/USDT:1m",
                        store=store,
                        hub=hub,
                        plot_orchestrator=None,
                        factor_orchestrator=None,
                        overlay_orchestrator=None,
                        settings=settings,
                        stop=stop,
                    )
                )
                try:
                    await asyncio.wait_for(fetched.wait(), timeout=1.0)
                finally:
                    stop.set()
                    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)

            self.assertEqual(seen.get("symbol"), "BTC/USDT:USDT")  # critical mapping
            self.assertEqual(seen.get("timeframe"), "1m")

            with store.connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM candles WHERE series_id = ?",
                    ("binance:futures:BTC/USDT:1m",),
                ).fetchone()
                self.assertEqual(int(row["n"]), 1)

        asyncio.run(test_body())

    def test_ingest_flush_runs_in_blocking_executor(self) -> None:
        async def test_body() -> None:
            store = CandleStore(db_path=self.db_path)
            hub = CandleHub()
            stop = asyncio.Event()
            fetched = asyncio.Event()
            persisted = asyncio.Event()
            seen: dict[str, object] = {"to_thread_calls": 0}

            async def fake_fetch_ohlcv(exchange, symbol: str, timeframe: str, since_ms: int | None, limit: int):
                fetched.set()
                await asyncio.sleep(0)
                # One closed candle (ms) far enough in the past.
                return [[9_000_000, 1, 2, 0.5, 1.5, 10]]

            async def fake_to_thread(fn, *args, **kwargs):
                seen["to_thread_calls"] = int(seen.get("to_thread_calls", 0)) + 1
                out = fn(*args, **kwargs)
                persisted.set()
                return out

            with (
                patch("backend.app.ingest_ccxt._make_exchange_client", return_value=object()),
                patch("backend.app.ingest_ccxt._fetch_ohlcv", side_effect=fake_fetch_ohlcv),
                patch("backend.app.ingest_ccxt.run_blocking", side_effect=fake_to_thread),
                patch("backend.app.ingest_ccxt.time.time", return_value=10_000),
            ):
                settings = WhitelistIngestSettings(grace_window_s=0, poll_interval_s=0.01, batch_limit=10)

                task = asyncio.create_task(
                    run_whitelist_ingest_loop(
                        series_id="binance:spot:BTC/USDT:1m",
                        store=store,
                        hub=hub,
                        plot_orchestrator=None,
                        factor_orchestrator=None,
                        overlay_orchestrator=None,
                        settings=settings,
                        stop=stop,
                    )
                )
                try:
                    await asyncio.wait_for(fetched.wait(), timeout=1.0)
                    await asyncio.wait_for(persisted.wait(), timeout=1.0)
                finally:
                    stop.set()
                    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)

            self.assertGreaterEqual(int(seen.get("to_thread_calls") or 0), 1)

        asyncio.run(test_body())


if __name__ == "__main__":
    unittest.main()
