from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.ingest.supervisor import IngestSupervisor, _Job
from backend.app.store import CandleStore
from backend.app.ws.hub import CandleHub


class IngestSupervisorRoleGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.series_id = "binance:spot:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    @staticmethod
    def _fake_start_job(self, series_id: str, *, refcount: int) -> _Job:  # noqa: ANN001
        stop = asyncio.Event()

        async def _worker() -> None:
            await stop.wait()

        task = asyncio.create_task(_worker())
        return _Job(
            series_id=series_id,
            stop=stop,
            task=task,
            source="binance_ws",
            refcount=refcount,
            last_zero_at=None,
            started_at=time.time(),
        )

    def test_role_guard_read_mode_does_not_start_jobs_but_keeps_subscribe_success(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(self.series_id,),
            whitelist_ingest_enabled=True,
            enable_role_guard=True,
            ingest_role="read",
        )

        def _should_not_start(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("read_role_should_not_start_ingest_job")

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=_should_not_start):
                await sup.start_whitelist()
                await sup.start_reaper()
                ok = await sup.subscribe("binance:spot:ETH/USDT:1m")
                self.assertTrue(ok)
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 0)
                self.assertTrue(bool(snap["ingest_role_guard_enabled"]))
                self.assertEqual(str(snap["ingest_role"]), "read")
                self.assertFalse(bool(snap["ingest_jobs_enabled"]))
                self.assertFalse(sup.ingest_jobs_enabled)
                self.assertIsNone(getattr(sup, "_reaper_task", None))
            await sup.close()

        asyncio.run(run())

    def test_role_guard_ingest_mode_keeps_existing_start_behavior(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(),
            enable_role_guard=True,
            ingest_role="ingest",
        )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=self._fake_start_job):
                ok = await sup.subscribe(self.series_id)
                self.assertTrue(ok)
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertTrue(bool(snap["ingest_jobs_enabled"]))
                self.assertTrue(sup.ingest_jobs_enabled)
            await sup.close()

        asyncio.run(run())

    def test_role_guard_off_keeps_backward_compatible_behavior(self) -> None:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        sup = IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(),
            enable_role_guard=False,
            ingest_role="read",
        )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=self._fake_start_job):
                ok = await sup.subscribe(self.series_id)
                self.assertTrue(ok)
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertFalse(bool(snap["ingest_role_guard_enabled"]))
                self.assertEqual(str(snap["ingest_role"]), "read")
                self.assertTrue(bool(snap["ingest_jobs_enabled"]))
            await sup.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
