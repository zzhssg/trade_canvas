from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from .ingest_ccxt import WhitelistIngestSettings, run_whitelist_ingest_loop
from .series_id import parse_series_id
from .store import CandleStore
from .ws_hub import CandleHub
from .plot_orchestrator import PlotOrchestrator
from .factor_orchestrator import FactorOrchestrator
from .overlay_orchestrator import OverlayOrchestrator


@dataclass
class _Job:
    series_id: str
    stop: asyncio.Event
    task: asyncio.Task
    source: str
    refcount: int
    last_zero_at: float | None
    started_at: float
    crashes: int = 0
    last_crash_at: float | None = None


class IngestSupervisor:
    def __init__(
        self,
        *,
        store: CandleStore,
        hub: CandleHub,
        plot_orchestrator: PlotOrchestrator | None = None,
        factor_orchestrator: FactorOrchestrator | None = None,
        overlay_orchestrator: OverlayOrchestrator | None = None,
        whitelist_series_ids: tuple[str, ...],
        ingest_settings: WhitelistIngestSettings | None = None,
        ondemand_idle_ttl_s: int = 60,
    ) -> None:
        self._store = store
        self._hub = hub
        self._plot_orchestrator = plot_orchestrator
        self._factor_orchestrator = factor_orchestrator
        self._overlay_orchestrator = overlay_orchestrator
        self._whitelist = set(whitelist_series_ids)
        self._settings = ingest_settings or WhitelistIngestSettings()
        self._idle_ttl_s = ondemand_idle_ttl_s
        self._lock = asyncio.Lock()
        self._jobs: dict[str, _Job] = {}
        self._reaper_stop = asyncio.Event()
        self._reaper_task: asyncio.Task | None = None

    async def start_reaper(self) -> None:
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def start_whitelist(self) -> None:
        async with self._lock:
            for series_id in self._whitelist:
                if series_id in self._jobs:
                    continue
                job = self._start_job(series_id, refcount=-1)
                self._jobs[series_id] = job

    async def subscribe(self, series_id: str) -> bool:
        if series_id in self._whitelist:
            return True

        now = time.time()
        to_stop: list[_Job] = []

        async with self._lock:
            job = self._jobs.get(series_id)
            if job is None:
                max_jobs_raw = (os.environ.get("TRADE_CANVAS_ONDEMAND_MAX_JOBS") or "").strip()
                max_jobs = 0
                if max_jobs_raw:
                    try:
                        max_jobs = max(0, int(max_jobs_raw))
                    except ValueError:
                        max_jobs = 0

                if max_jobs > 0:
                    non_whitelist = [j for sid, j in self._jobs.items() if sid not in self._whitelist]
                    if len(non_whitelist) >= max_jobs:
                        idle = [
                            j
                            for sid, j in self._jobs.items()
                            if sid not in self._whitelist and j.refcount == 0 and j.last_zero_at is not None
                        ]
                        idle.sort(key=lambda j: float(j.last_zero_at or now))
                        if idle:
                            victim = idle[0]
                            self._jobs.pop(victim.series_id, None)
                            to_stop.append(victim)
                        else:
                            return False

                job = self._start_job(series_id, refcount=0)
                self._jobs[series_id] = job

            job.refcount += 1
            job.last_zero_at = None

        for job in to_stop:
            job.stop.set()
            job.task.cancel()

        return True

    async def unsubscribe(self, series_id: str) -> None:
        if series_id in self._whitelist:
            return
        async with self._lock:
            job = self._jobs.get(series_id)
            if job is None:
                return
            job.refcount = max(0, job.refcount - 1)
            if job.refcount == 0:
                job.last_zero_at = time.time()

    async def close(self) -> None:
        async with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for job in jobs:
            job.stop.set()
            job.task.cancel()
        if jobs:
            await asyncio.gather(*(j.task for j in jobs), return_exceptions=True)

        if self._reaper_task is not None:
            self._reaper_stop.set()
            self._reaper_task.cancel()
            await asyncio.gather(self._reaper_task, return_exceptions=True)

    async def debug_snapshot(self) -> dict:
        async with self._lock:
            jobs = [
                {
                    "series_id": j.series_id,
                    "source": j.source,
                    "refcount": j.refcount,
                    "last_zero_at": j.last_zero_at,
                    "started_at": j.started_at,
                    "crashes": j.crashes,
                    "last_crash_at": j.last_crash_at,
                    "running": bool(not j.task.done()),
                }
                for j in self._jobs.values()
            ]
            jobs.sort(key=lambda x: x["series_id"])
            max_jobs_raw = (os.environ.get("TRADE_CANVAS_ONDEMAND_MAX_JOBS") or "").strip()
            try:
                max_jobs = int(max_jobs_raw) if max_jobs_raw else 0
            except ValueError:
                max_jobs = 0
            return {
                "jobs": jobs,
                "whitelist_series_ids": sorted(self._whitelist),
                "ondemand_max_jobs": max_jobs,
            }

    def _start_job(self, series_id: str, *, refcount: int) -> _Job:
        stop = asyncio.Event()
        realtime = (os.environ.get("TRADE_CANVAS_MARKET_REALTIME_SOURCE") or "ccxt").strip().lower()
        ingest_fn = run_whitelist_ingest_loop
        source = "ccxt"
        if realtime == "binance_ws":
            try:
                series = parse_series_id(series_id)
                if series.exchange == "binance":
                    from .ingest_binance_ws import run_binance_ws_ingest_loop

                    ingest_fn = run_binance_ws_ingest_loop
                    source = "binance_ws"
            except Exception:
                ingest_fn = run_whitelist_ingest_loop

        started_at = time.time()

        async def runner() -> None:
            try:
                await ingest_fn(
                    series_id=series_id,
                    store=self._store,
                    hub=self._hub,
                    plot_orchestrator=self._plot_orchestrator,
                    factor_orchestrator=self._factor_orchestrator,
                    overlay_orchestrator=self._overlay_orchestrator,
                    settings=self._settings,
                    stop=stop,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                async with self._lock:
                    job = self._jobs.get(series_id)
                    if job is not None:
                        job.crashes += 1
                        job.last_crash_at = time.time()
                await asyncio.sleep(2.0)

        task = asyncio.create_task(runner())
        return _Job(
            series_id=series_id,
            stop=stop,
            task=task,
            source=source,
            refcount=refcount,
            last_zero_at=None,
            started_at=started_at,
        )

    async def _reaper_loop(self) -> None:
        while not self._reaper_stop.is_set():
            await asyncio.sleep(1.0)
            now = time.time()
            to_stop: list[_Job] = []
            async with self._lock:
                for series_id, job in list(self._jobs.items()):
                    if series_id in self._whitelist:
                        continue
                    if job.refcount != 0 or job.last_zero_at is None:
                        continue
                    if now - job.last_zero_at < self._idle_ttl_s:
                        continue
                    to_stop.append(job)
                    self._jobs.pop(series_id, None)

            for job in to_stop:
                job.stop.set()
                job.task.cancel()
            if to_stop:
                await asyncio.gather(*(j.task for j in to_stop), return_exceptions=True)
