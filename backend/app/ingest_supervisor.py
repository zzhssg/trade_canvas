from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .ingest_capacity_policy import plan_ondemand_capacity
from .ingest_guardrail_registry import IngestGuardrailRegistry
from .ingest_job_runner import IngestJobRunner, IngestJobRunnerConfig, IngestLoopFn
from .ingest_loop_guardrail import IngestLoopGuardrail, IngestLoopGuardrailConfig
from .ingest_restart_policy import carry_restart_state, mark_restart_failure, plan_ingest_restart
from .ingest_reaper_policy import IngestReaperJobState, plan_ingest_reaper
from .ingest_series_router import IngestSeriesRouter, IngestSeriesRouterConfig
from .ingest_source_registry import IngestSourceBinding, IngestSourceRegistry
from .ingest_binance_ws import run_binance_ws_ingest_loop
from .ingest_settings import WhitelistIngestSettings
from .pipelines import IngestPipeline
from .store import CandleStore
from .ws_hub import CandleHub


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
    guardrail: IngestLoopGuardrail | None = None


@dataclass(frozen=True)
class _JobStartPlan:
    series_id: str
    refcount: int
    stop: asyncio.Event
    source: str
    ingest_fn: IngestLoopFn
    guardrail: IngestLoopGuardrail | None
    started_at: float


class IngestSupervisor:
    def __init__(
        self,
        *,
        store: CandleStore,
        hub: CandleHub,
        whitelist_series_ids: tuple[str, ...],
        ingest_settings: WhitelistIngestSettings | None = None,
        ondemand_idle_ttl_s: int = 60,
        ondemand_max_jobs: int = 0,
        whitelist_ingest_enabled: bool = False,
        ingest_pipeline: IngestPipeline | None = None,
        market_history_source: str = "",
        derived_enabled: bool = False,
        derived_base_timeframe: str = "1m",
        derived_timeframes: tuple[str, ...] = (),
        binance_ws_batch_max: int = 200,
        binance_ws_flush_s: float = 0.5,
        forming_min_interval_ms: int = 250,
        enable_loop_guardrail: bool = False,
        guardrail_crash_budget: int = 5,
        guardrail_budget_window_s: float = 60.0,
        guardrail_backoff_initial_s: float = 1.0,
        guardrail_backoff_max_s: float = 15.0,
        guardrail_open_cooldown_s: float = 30.0,
        enable_role_guard: bool = False,
        ingest_role: str = "hybrid",
    ) -> None:
        self._whitelist = set(whitelist_series_ids)
        self._whitelist_ingest_enabled = bool(whitelist_ingest_enabled)
        self._ingest_role_guard_enabled = bool(enable_role_guard)
        self._ingest_role = self._normalize_ingest_role(ingest_role)
        self._ingest_jobs_enabled = (not self._ingest_role_guard_enabled) or self._ingest_role in {"hybrid", "ingest"}
        self._settings = ingest_settings or WhitelistIngestSettings()
        self._idle_ttl_s = ondemand_idle_ttl_s
        self._ondemand_max_jobs = max(0, int(ondemand_max_jobs))
        self._ingest_pipeline = ingest_pipeline
        self._market_history_source = str(market_history_source or "").strip().lower()
        self._derived_enabled = bool(derived_enabled)
        self._derived_base_timeframe = str(derived_base_timeframe).strip() or "1m"
        self._derived_timeframes = tuple(str(tf).strip() for tf in (derived_timeframes or ()) if str(tf).strip())
        self._binance_ws_batch_max = max(1, int(binance_ws_batch_max))
        self._binance_ws_flush_s = max(0.05, float(binance_ws_flush_s))
        self._forming_min_interval_ms = max(0, int(forming_min_interval_ms))
        self._source_registry = IngestSourceRegistry(
            bindings={
                "binance": IngestSourceBinding(
                    source="binance_ws",
                    get_ingest_fn=lambda: run_binance_ws_ingest_loop,
                )
            }
        )
        self._series_router = IngestSeriesRouter(
            source_registry=self._source_registry,
            config=IngestSeriesRouterConfig(
                derived_enabled=self._derived_enabled,
                derived_base_timeframe=self._derived_base_timeframe,
                derived_timeframes=self._derived_timeframes,
            ),
        )
        self._job_runner = IngestJobRunner(
            store=store,
            hub=hub,
            ingest_pipeline=self._ingest_pipeline,
            settings=self._settings,
            config=IngestJobRunnerConfig(
                market_history_source=self._market_history_source,
                derived_enabled=self._derived_enabled,
                derived_base_timeframe=self._derived_base_timeframe,
                derived_timeframes=self._derived_timeframes,
                batch_max=self._binance_ws_batch_max,
                flush_s=self._binance_ws_flush_s,
                forming_min_interval_ms=self._forming_min_interval_ms,
            ),
        )
        self._guardrails = IngestGuardrailRegistry(
            enabled=bool(enable_loop_guardrail),
            config=IngestLoopGuardrailConfig(
                crash_budget=max(1, int(guardrail_crash_budget)),
                budget_window_s=max(1.0, float(guardrail_budget_window_s)),
                backoff_initial_s=max(0.0, float(guardrail_backoff_initial_s)),
                backoff_max_s=max(0.0, float(guardrail_backoff_max_s)),
                open_cooldown_s=max(0.0, float(guardrail_open_cooldown_s)),
            ),
        )
        self._lock = asyncio.Lock()
        self._jobs: dict[str, _Job] = {}
        self._reaper_stop = asyncio.Event()
        self._reaper_task: asyncio.Task | None = None

    @staticmethod
    def _normalize_ingest_role(value: str) -> str:
        role = str(value or "").strip().lower()
        if role in {"hybrid", "ingest", "read"}:
            return role
        return "hybrid"

    async def _stop_jobs(self, *, jobs: list[_Job], wait: bool) -> None:
        if not jobs:
            return
        for job in jobs:
            job.stop.set()
            job.task.cancel()
        if bool(wait):
            await asyncio.gather(*(job.task for job in jobs), return_exceptions=True)

    def _drop_job_locked(self, *, series_id: str, drop_guardrail: bool) -> _Job | None:
        job = self._jobs.pop(series_id, None)
        if bool(drop_guardrail):
            self._guardrails.drop(series_id)
        return job

    def _start_and_track_job_locked(self, *, series_id: str, refcount: int) -> _Job:
        job = self._start_job(series_id, refcount=int(refcount))
        self._jobs[series_id] = job
        return job

    def _apply_subscribe_locked(self, *, series_id: str, now: float) -> tuple[bool, list[_Job]]:
        to_stop: list[_Job] = []
        job = self._jobs.get(series_id)
        if job is not None and job.task.done():
            guardrail = job.guardrail
            if guardrail is not None:
                wait_s = float(guardrail.before_attempt())
                if wait_s > 0:
                    return False, to_stop
            self._drop_job_locked(
                series_id=series_id,
                drop_guardrail=False,
            )
            job = None
        if job is None:
            capacity_plan = plan_ondemand_capacity(
                jobs=self._jobs.values(),
                max_jobs=int(self._ondemand_max_jobs),
                is_pinned_whitelist=self._is_pinned_whitelist,
                now=now,
            )
            if not bool(capacity_plan.accepted):
                return False, to_stop
            victim_series_id = capacity_plan.victim_series_id
            if victim_series_id is not None:
                victim = self._drop_job_locked(
                    series_id=victim_series_id,
                    drop_guardrail=True,
                )
                if victim is not None:
                    to_stop.append(victim)

            try:
                job = self._start_and_track_job_locked(
                    series_id=series_id,
                    refcount=0,
                )
            except Exception:
                return False, to_stop

        job.refcount += 1
        job.last_zero_at = None
        return True, to_stop

    def _plan_reaper_locked(self, *, now: float) -> tuple[list[_Job], list[tuple[str, _Job]]]:
        to_stop: list[_Job] = []
        to_restart: list[tuple[str, _Job]] = []
        reaper_plan = plan_ingest_reaper(
            jobs=(
                IngestReaperJobState(
                    series_id=series_id,
                    refcount=int(job.refcount),
                    last_zero_at=job.last_zero_at,
                    task_done=bool(job.task.done()),
                )
                for series_id, job in self._jobs.items()
            ),
            now=now,
            idle_ttl_s=float(self._idle_ttl_s),
            is_pinned_whitelist=self._is_pinned_whitelist,
        )
        stop_series_ids = set(reaper_plan.stop_series_ids)
        for series_id in reaper_plan.drop_series_ids:
            job = self._drop_job_locked(
                series_id=series_id,
                drop_guardrail=True,
            )
            if job is None:
                continue
            if series_id in stop_series_ids:
                to_stop.append(job)
        for series_id in reaper_plan.restart_series_ids:
            snapshot = self._jobs.get(series_id)
            if snapshot is not None:
                to_restart.append((series_id, snapshot))
        return to_stop, to_restart

    async def start_reaper(self) -> None:
        if not self._ingest_jobs_enabled:
            return
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def start_whitelist(self) -> None:
        if not self._ingest_jobs_enabled:
            return
        if not self._whitelist_ingest_enabled:
            return
        async with self._lock:
            for series_id in self._whitelist:
                if series_id in self._jobs:
                    continue
                self._start_and_track_job_locked(
                    series_id=series_id,
                    refcount=-1,
                )

    async def subscribe(self, series_id: str) -> bool:
        series_id = self._series_router.normalize(series_id)
        if self._is_pinned_whitelist(series_id):
            return True
        if not self._ingest_jobs_enabled:
            return True

        now = time.time()
        async with self._lock:
            accepted, to_stop = self._apply_subscribe_locked(series_id=series_id, now=now)

        await self._stop_jobs(jobs=to_stop, wait=False)
        return bool(accepted)

    async def unsubscribe(self, series_id: str) -> None:
        series_id = self._series_router.normalize(series_id)
        if self._is_pinned_whitelist(series_id):
            return
        if not self._ingest_jobs_enabled:
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
            self._guardrails.clear()
        await self._stop_jobs(jobs=jobs, wait=True)

        if self._reaper_task is not None:
            self._reaper_stop.set()
            self._reaper_task.cancel()
            await asyncio.gather(self._reaper_task, return_exceptions=True)

    @staticmethod
    def _job_debug_payload(job: _Job) -> dict[str, object]:
        return {
            "series_id": str(job.series_id),
            "source": str(job.source),
            "refcount": int(job.refcount),
            "last_zero_at": job.last_zero_at,
            "started_at": float(job.started_at),
            "crashes": int(job.crashes),
            "last_crash_at": job.last_crash_at,
            "running": bool(not job.task.done()),
            "guardrail": None if job.guardrail is None else job.guardrail.snapshot(),
        }

    def _build_debug_snapshot_locked(self) -> dict[str, object]:
        jobs = [self._job_debug_payload(job) for job in self._jobs.values()]
        jobs.sort(key=lambda item: str(item["series_id"]))
        return {
            "jobs": jobs,
            "whitelist_series_ids": sorted(self._whitelist),
            "ondemand_max_jobs": int(self._ondemand_max_jobs),
            "whitelist_ingest_enabled": bool(self._whitelist_ingest_enabled),
            "ingest_role_guard_enabled": bool(self._ingest_role_guard_enabled),
            "ingest_role": str(self._ingest_role),
            "ingest_jobs_enabled": bool(self._ingest_jobs_enabled),
            "loop_guardrail_enabled": bool(self._guardrails.enabled),
        }

    async def debug_snapshot(self) -> dict:
        async with self._lock:
            return self._build_debug_snapshot_locked()

    @property
    def whitelist_ingest_enabled(self) -> bool:
        return bool(self._whitelist_ingest_enabled)

    @property
    def ingest_jobs_enabled(self) -> bool:
        return bool(self._ingest_jobs_enabled)

    def _plan_job_start(self, *, series_id: str, refcount: int) -> _JobStartPlan:
        stop = asyncio.Event()
        source_binding = self._series_router.resolve_source(series_id=series_id)
        return _JobStartPlan(
            series_id=str(series_id),
            refcount=int(refcount),
            stop=stop,
            source=str(source_binding.source),
            ingest_fn=source_binding.get_ingest_fn(),
            guardrail=self._guardrails.get(series_id),
            started_at=float(time.time()),
        )

    def _run_job_start(self, *, plan: _JobStartPlan) -> asyncio.Task:
        return self._job_runner.start(
            series_id=plan.series_id,
            stop=plan.stop,
            guardrail=plan.guardrail,
            ingest_fn=plan.ingest_fn,
            on_crash=self._record_job_crash,
        )

    @staticmethod
    def _build_job_from_start(*, plan: _JobStartPlan, task: asyncio.Task) -> _Job:
        return _Job(
            series_id=plan.series_id,
            stop=plan.stop,
            task=task,
            source=plan.source,
            refcount=plan.refcount,
            last_zero_at=None,
            started_at=plan.started_at,
            guardrail=plan.guardrail,
        )

    def _start_job(self, series_id: str, *, refcount: int) -> _Job:
        plan = self._plan_job_start(
            series_id=series_id,
            refcount=int(refcount),
        )
        task = self._run_job_start(plan=plan)
        return self._build_job_from_start(
            plan=plan,
            task=task,
        )

    async def _record_job_crash(self, series_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(series_id)
            if job is None:
                return
            job.crashes += 1
            job.last_crash_at = time.time()

    async def _reaper_loop(self) -> None:
        while not self._reaper_stop.is_set():
            await asyncio.sleep(1.0)
            now = time.time()
            async with self._lock:
                to_stop, to_restart = self._plan_reaper_locked(now=now)

            await self._stop_jobs(jobs=to_stop, wait=True)
            for series_id, snapshot in to_restart:
                await self._restart_dead_job(series_id=series_id, snapshot=snapshot)

    async def _restart_dead_job(self, *, series_id: str, snapshot: _Job) -> None:
        async with self._lock:
            current = self._jobs.get(series_id)
            restart_plan = plan_ingest_restart(
                current_is_snapshot=current is snapshot,
                guardrail=snapshot.guardrail,
            )
            if not bool(restart_plan.should_restart):
                return
            try:
                replacement = self._start_job(series_id, refcount=int(snapshot.refcount))
            except Exception:
                mark_restart_failure(job=snapshot, at=time.time())
                return
            carry_restart_state(source=snapshot, target=replacement)
            self._jobs[series_id] = replacement

    def _is_pinned_whitelist(self, series_id: str) -> bool:
        return self._whitelist_ingest_enabled and series_id in self._whitelist
