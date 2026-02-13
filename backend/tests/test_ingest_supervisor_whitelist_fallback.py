from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.ingest.supervisor import IngestSupervisor, _Job
from backend.app.storage.candle_store import CandleStore
from backend.app.ws.hub import CandleHub


class IngestSupervisorWhitelistFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _make_supervisor(self, *, whitelist_ingest_enabled: bool) -> IngestSupervisor:
        store = CandleStore(db_path=self.db_path)
        hub = CandleHub()
        return IngestSupervisor(
            store=store,
            hub=hub,
            whitelist_series_ids=(self.series_id,),
            whitelist_ingest_enabled=whitelist_ingest_enabled,
        )

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

    def test_whitelist_series_falls_back_to_ondemand_when_whitelist_ingest_disabled(self) -> None:
        sup = self._make_supervisor(whitelist_ingest_enabled=False)

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=self._fake_start_job):
                ok = await sup.subscribe(self.series_id)
                self.assertTrue(ok)
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertEqual(snap["jobs"][0]["series_id"], self.series_id)
                self.assertEqual(int(snap["jobs"][0]["refcount"]), 1)
                self.assertEqual(snap["jobs"][0]["source"], "binance_ws")
            await sup.close()

        asyncio.run(run())

    def test_whitelist_series_is_pinned_when_whitelist_ingest_enabled(self) -> None:
        sup = self._make_supervisor(whitelist_ingest_enabled=True)

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=self._fake_start_job):
                await sup.start_whitelist()
                snap0 = await sup.debug_snapshot()
                self.assertEqual(len(snap0["jobs"]), 1)
                self.assertEqual(int(snap0["jobs"][0]["refcount"]), -1)

                ok = await sup.subscribe(self.series_id)
                self.assertTrue(ok)
                snap1 = await sup.debug_snapshot()
                self.assertEqual(len(snap1["jobs"]), 1)
                self.assertEqual(int(snap1["jobs"][0]["refcount"]), -1)
            await sup.close()

        asyncio.run(run())

    def test_reaper_restarts_dead_pinned_whitelist_job(self) -> None:
        sup = self._make_supervisor(whitelist_ingest_enabled=True)
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
                source="binance_ws",
                refcount=refcount,
                last_zero_at=None,
                started_at=time.time(),
            )

        async def run() -> None:
            with patch.object(IngestSupervisor, "_start_job", new=_fake_start_job):
                await sup.start_whitelist()
                await sup.start_reaper()
                await asyncio.sleep(2.2)
                self.assertEqual(starts, [self.series_id, self.series_id])
                snap = await sup.debug_snapshot()
                self.assertEqual(len(snap["jobs"]), 1)
                self.assertEqual(int(snap["jobs"][0]["refcount"]), -1)
                self.assertTrue(bool(snap["jobs"][0]["running"]))
            await sup.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
