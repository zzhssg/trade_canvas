from __future__ import annotations

import asyncio
import time

from .config import IngestRuntimeConfig
from .guardrail_registry import IngestGuardrailRegistry
from .job_runner import IngestJobRunner, IngestJobRunnerConfig, IngestLoopFn
from .loop_guardrail import IngestLoopGuardrail, IngestLoopGuardrailConfig
from .restart_policy import carry_restart_state, mark_restart_failure, plan_ingest_restart
from .series_router import IngestSeriesRouter, IngestSeriesRouterConfig
from .source_registry import IngestSourceBinding, IngestSourceRegistry
from .supervisor_support import (
    _Job,
    _JobStartPlan,
    apply_subscribe_locked,
    build_debug_snapshot_locked,
    normalize_ingest_role,
    plan_reaper_locked,
    start_and_track_job_locked,
    stop_jobs,
)
from .binance_ws import run_binance_ws_ingest_loop
from .settings import WhitelistIngestSettings
from ..pipelines import IngestPipeline
from ..storage.candle_store import CandleStore
from ..ws.hub import CandleHub


class IngestSupervisor:
    def __init__(
        self,
        *,
        store: CandleStore,
        hub: CandleHub,
        whitelist_series_ids: tuple[str, ...],
        ingest_settings: WhitelistIngestSettings | None = None,
        ondemand_idle_ttl_s: int = 60,
        whitelist_ingest_enabled: bool = False,
        ingest_pipeline: IngestPipeline | None = None,
        config: IngestRuntimeConfig | None = None,
    ) -> None:
        cfg = config or IngestRuntimeConfig()
        self._whitelist = set(whitelist_series_ids)
        self._whitelist_ingest_enabled = bool(whitelist_ingest_enabled)
        self._ingest_role_guard_enabled = bool(cfg.role_guard_enabled)
        self._ingest_role = normalize_ingest_role(cfg.ingest_role)
        self._ingest_jobs_enabled = (not self._ingest_role_guard_enabled) or self._ingest_role in {"hybrid", "ingest"}
        self._settings = ingest_settings or WhitelistIngestSettings()
        self._idle_ttl_s = ondemand_idle_ttl_s
        self._ondemand_max_jobs = max(0, int(cfg.ondemand_max_jobs))
        self._ingest_pipeline = ingest_pipeline
        self._market_history_source = str(cfg.market_history_source or "").strip().lower()
        self._derived_enabled = bool(cfg.derived_enabled)
        self._derived_base_timeframe = str(cfg.derived_base_timeframe).strip() or "1m"
        self._derived_timeframes = tuple(str(tf).strip() for tf in (cfg.derived_timeframes or ()) if str(tf).strip())
        self._binance_ws_batch_max = max(1, int(cfg.ws_batch_max))
        self._binance_ws_flush_s = max(0.05, float(cfg.ws_flush_s))
        self._forming_min_interval_ms = max(0, int(cfg.forming_min_interval_ms))
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
            enabled=bool(cfg.loop_guardrail_enabled),
            config=IngestLoopGuardrailConfig(
                crash_budget=max(1, int(cfg.guardrail_crash_budget)),
                budget_window_s=max(1.0, float(cfg.guardrail_budget_window_s)),
                backoff_initial_s=max(0.0, float(cfg.guardrail_backoff_initial_s)),
                backoff_max_s=max(0.0, float(cfg.guardrail_backoff_max_s)),
                open_cooldown_s=max(0.0, float(cfg.guardrail_open_cooldown_s)),
            ),
        )
        self._lock = asyncio.Lock()
        self._jobs: dict[str, _Job] = {}
        self._reaper_stop = asyncio.Event()
        self._reaper_task: asyncio.Task | None = None

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
                start_and_track_job_locked(
                    jobs=self._jobs,
                    series_id=series_id,
                    refcount=-1,
                    start_job=self._start_job,
                )

    async def subscribe(self, series_id: str) -> bool:
        series_id = self._series_router.normalize(series_id)
        if self._is_pinned_whitelist(series_id):
            return True
        if not self._ingest_jobs_enabled:
            return True

        now = time.time()
        async with self._lock:
            accepted, to_stop = apply_subscribe_locked(
                jobs=self._jobs,
                series_id=series_id,
                now=now,
                ondemand_max_jobs=self._ondemand_max_jobs,
                is_pinned_whitelist=self._is_pinned_whitelist,
                guardrails=self._guardrails,
                start_job=self._start_job,
            )

        await stop_jobs(jobs=to_stop, wait=False)
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
        await stop_jobs(jobs=jobs, wait=True)

        if self._reaper_task is not None:
            self._reaper_stop.set()
            self._reaper_task.cancel()
            await asyncio.gather(self._reaper_task, return_exceptions=True)

    async def debug_snapshot(self) -> dict:
        async with self._lock:
            return build_debug_snapshot_locked(
                jobs=self._jobs,
                whitelist=self._whitelist,
                ondemand_max_jobs=self._ondemand_max_jobs,
                whitelist_ingest_enabled=self._whitelist_ingest_enabled,
                ingest_role_guard_enabled=self._ingest_role_guard_enabled,
                ingest_role=self._ingest_role,
                ingest_jobs_enabled=self._ingest_jobs_enabled,
                loop_guardrail_enabled=self._guardrails.enabled,
            )

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
                to_stop, to_restart = plan_reaper_locked(
                    jobs=self._jobs,
                    now=now,
                    idle_ttl_s=self._idle_ttl_s,
                    is_pinned_whitelist=self._is_pinned_whitelist,
                    guardrails=self._guardrails,
                )

            await stop_jobs(jobs=to_stop, wait=True)
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
