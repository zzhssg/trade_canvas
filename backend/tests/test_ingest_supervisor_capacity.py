from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.ingest_supervisor import IngestSupervisor, _Job
from backend.app.store import CandleStore
from backend.app.ws_hub import CandleHub


class IngestSupervisorCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_capacity_denies_when_full_and_no_idle(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(store=store, hub=hub, whitelist_series_ids=(), ondemand_max_jobs=1)

        def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
            stop = asyncio.Event()

            async def _worker() -> None:
                await stop.wait()

            task = asyncio.create_task(_worker())
            return _Job(
                series_id=series_id,
                stop=stop,
                task=task,
                source="test",
                refcount=refcount,
                last_zero_at=None,
                started_at=time.time(),
            )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=_fake_start_job):
                ok1 = await sup.subscribe("binance:spot:BTC/USDT:1m")
                ok2 = await sup.subscribe("binance:spot:ETH/USDT:1m")
                self.assertTrue(ok1)
                self.assertFalse(ok2)
            await sup.close()

        asyncio.run(run())

    def test_capacity_evicts_idle_job(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(store=store, hub=hub, whitelist_series_ids=(), ondemand_max_jobs=1)

        def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
            stop = asyncio.Event()

            async def _worker() -> None:
                await stop.wait()

            task = asyncio.create_task(_worker())
            return _Job(
                series_id=series_id,
                stop=stop,
                task=task,
                source="test",
                refcount=refcount,
                last_zero_at=None,
                started_at=time.time(),
            )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=_fake_start_job):
                ok1 = await sup.subscribe("binance:spot:BTC/USDT:1m")
                self.assertTrue(ok1)
                await sup.unsubscribe("binance:spot:BTC/USDT:1m")
                ok2 = await sup.subscribe("binance:spot:ETH/USDT:1m")
                self.assertTrue(ok2)
                snap = await sup.debug_snapshot()
                series_ids = [j["series_id"] for j in snap["jobs"]]
                self.assertIn("binance:spot:ETH/USDT:1m", series_ids)
            await sup.close()

        asyncio.run(run())

    def test_derived_subscription_maps_to_base_job(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(),
            derived_enabled=True,
            derived_base_timeframe="1m",
            derived_timeframes=("5m",),
        )
        started: list[str] = []

        def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
            started.append(series_id)
            stop = asyncio.Event()

            async def _worker() -> None:
                await stop.wait()

            task = asyncio.create_task(_worker())
            return _Job(
                series_id=series_id,
                stop=stop,
                task=task,
                source="test",
                refcount=refcount,
                last_zero_at=None,
                started_at=time.time(),
            )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=_fake_start_job):
                ok = await sup.subscribe("binance:spot:BTC/USDT:5m")
                self.assertTrue(ok)
                self.assertEqual(started, ["binance:spot:BTC/USDT:1m"])
                await sup.unsubscribe("binance:spot:BTC/USDT:5m")
            await sup.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
