from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from .capacity_policy import plan_ondemand_capacity
from .guardrail_registry import IngestGuardrailRegistry
from .job_runner import IngestLoopFn
from .loop_guardrail import IngestLoopGuardrail
from .reaper_policy import IngestReaperJobState, plan_ingest_reaper


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


def normalize_ingest_role(value: str) -> str:
    role = str(value or "").strip().lower()
    if role in {"hybrid", "ingest", "read"}:
        return role
    return "hybrid"


async def stop_jobs(*, jobs: list[_Job], wait: bool) -> None:
    if not jobs:
        return
    for job in jobs:
        job.stop.set()
        job.task.cancel()
    if bool(wait):
        await asyncio.gather(*(job.task for job in jobs), return_exceptions=True)


def drop_job_locked(
    *,
    jobs: dict[str, _Job],
    guardrails: IngestGuardrailRegistry,
    series_id: str,
    drop_guardrail: bool,
) -> _Job | None:
    job = jobs.pop(series_id, None)
    if bool(drop_guardrail):
        guardrails.drop(series_id)
    return job


def start_and_track_job_locked(
    *,
    jobs: dict[str, _Job],
    series_id: str,
    refcount: int,
    start_job: Callable[..., _Job],
) -> _Job:
    job = start_job(series_id, refcount=int(refcount))
    jobs[series_id] = job
    return job


def apply_subscribe_locked(
    *,
    jobs: dict[str, _Job],
    series_id: str,
    now: float,
    ondemand_max_jobs: int,
    is_pinned_whitelist: Callable[[str], bool],
    guardrails: IngestGuardrailRegistry,
    start_job: Callable[..., _Job],
) -> tuple[bool, list[_Job]]:
    to_stop: list[_Job] = []
    job = jobs.get(series_id)
    if job is not None and job.task.done():
        guardrail = job.guardrail
        if guardrail is not None:
            wait_s = float(guardrail.before_attempt())
            if wait_s > 0:
                return False, to_stop
        drop_job_locked(
            jobs=jobs,
            guardrails=guardrails,
            series_id=series_id,
            drop_guardrail=False,
        )
        job = None
    if job is None:
        capacity_plan = plan_ondemand_capacity(
            jobs=jobs.values(),
            max_jobs=int(ondemand_max_jobs),
            is_pinned_whitelist=is_pinned_whitelist,
            now=now,
        )
        if not bool(capacity_plan.accepted):
            return False, to_stop
        victim_series_id = capacity_plan.victim_series_id
        if victim_series_id is not None:
            victim = drop_job_locked(
                jobs=jobs,
                guardrails=guardrails,
                series_id=victim_series_id,
                drop_guardrail=True,
            )
            if victim is not None:
                to_stop.append(victim)
        try:
            job = start_and_track_job_locked(
                jobs=jobs,
                series_id=series_id,
                refcount=0,
                start_job=start_job,
            )
        except Exception:
            return False, to_stop
    job.refcount += 1
    job.last_zero_at = None
    return True, to_stop


def plan_reaper_locked(
    *,
    jobs: dict[str, _Job],
    now: float,
    idle_ttl_s: int,
    is_pinned_whitelist: Callable[[str], bool],
    guardrails: IngestGuardrailRegistry,
) -> tuple[list[_Job], list[tuple[str, _Job]]]:
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
            for series_id, job in jobs.items()
        ),
        now=now,
        idle_ttl_s=float(idle_ttl_s),
        is_pinned_whitelist=is_pinned_whitelist,
    )
    stop_series_ids = set(reaper_plan.stop_series_ids)
    for series_id in reaper_plan.drop_series_ids:
        job = drop_job_locked(
            jobs=jobs,
            guardrails=guardrails,
            series_id=series_id,
            drop_guardrail=True,
        )
        if job is None:
            continue
        if series_id in stop_series_ids:
            to_stop.append(job)
    for series_id in reaper_plan.restart_series_ids:
        snapshot = jobs.get(series_id)
        if snapshot is not None:
            to_restart.append((series_id, snapshot))
    return to_stop, to_restart


def job_debug_payload(job: _Job) -> dict[str, object]:
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


def build_debug_snapshot_locked(
    *,
    jobs: dict[str, _Job],
    whitelist: set[str],
    ondemand_max_jobs: int,
    whitelist_ingest_enabled: bool,
    ingest_role_guard_enabled: bool,
    ingest_role: str,
    ingest_jobs_enabled: bool,
    loop_guardrail_enabled: bool,
) -> dict[str, object]:
    debug_jobs = [job_debug_payload(job) for job in jobs.values()]
    debug_jobs.sort(key=lambda item: str(item["series_id"]))
    return {
        "jobs": debug_jobs,
        "whitelist_series_ids": sorted(whitelist),
        "ondemand_max_jobs": int(ondemand_max_jobs),
        "whitelist_ingest_enabled": bool(whitelist_ingest_enabled),
        "ingest_role_guard_enabled": bool(ingest_role_guard_enabled),
        "ingest_role": str(ingest_role),
        "ingest_jobs_enabled": bool(ingest_jobs_enabled),
        "loop_guardrail_enabled": bool(loop_guardrail_enabled),
    }
