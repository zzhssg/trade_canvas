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

    def test_subscribe_restarts_dead_job(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(store=store, hub=hub, whitelist_series_ids=())
        series_id = "binance:spot:BTC/USDT:1m"
        starts: list[str] = []

        def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
            starts.append(series_id)
            stop = asyncio.Event()

            if len(starts) == 1:
                async def _worker() -> None:
                    return
            else:
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
                ok1 = await sup.subscribe(series_id)
                self.assertTrue(ok1)
                await asyncio.sleep(0)
                snap0 = await sup.debug_snapshot()
                self.assertEqual(len(snap0["jobs"]), 1)
                self.assertFalse(bool(snap0["jobs"][0]["running"]))

                ok2 = await sup.subscribe(series_id)
                self.assertTrue(ok2)
                await asyncio.sleep(0)
                self.assertEqual(starts, [series_id, series_id])
                snap1 = await sup.debug_snapshot()
                self.assertEqual(len(snap1["jobs"]), 1)
                self.assertTrue(bool(snap1["jobs"][0]["running"]))
            await sup.close()

        asyncio.run(run())

    def test_reaper_restarts_dead_active_ondemand_job(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(store=store, hub=hub, whitelist_series_ids=(), ondemand_idle_ttl_s=1)
        series_id = "binance:spot:BTC/USDT:1m"
        starts: list[str] = []

        def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
            starts.append(series_id)
            stop = asyncio.Event()

            if len(starts) == 1:
                async def _worker() -> None:
                    return
            else:
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
                ok = await sup.subscribe(series_id)
                self.assertTrue(ok)
                await sup.start_reaper()
                await asyncio.sleep(2.2)
                self.assertEqual(starts, [series_id, series_id])
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertEqual(int(snap["jobs"][0]["refcount"]), 1)
                self.assertTrue(bool(snap["jobs"][0]["running"]))
            await sup.close()

        asyncio.run(run())

    def test_guardrail_snapshot_exposed_when_enabled(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(),
            enable_loop_guardrail=True,
            guardrail_crash_budget=1,
            guardrail_open_cooldown_s=0.5,
        )
        series_id = "binance:spot:BTC/USDT:1m"

        async def _failing_ws_loop(**kwargs) -> None:  # noqa: ANN003
            _ = kwargs
            raise RuntimeError("ws_loop_failed")

        async def run() -> None:
            with patch("backend.app.ingest_supervisor.run_binance_ws_ingest_loop", new=_failing_ws_loop):
                ok = await sup.subscribe(series_id)
                self.assertTrue(ok)
                await asyncio.sleep(0.05)
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertTrue(bool(snap["loop_guardrail_enabled"]))
                guardrail = snap["jobs"][0].get("guardrail")
                self.assertIsInstance(guardrail, dict)
                assert isinstance(guardrail, dict)
                self.assertEqual(guardrail.get("state"), "open")
                self.assertGreaterEqual(int(guardrail.get("window_failures", 0)), 1)
            await sup.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
