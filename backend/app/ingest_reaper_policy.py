from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class IngestReaperJobState:
    series_id: str
    refcount: int
    last_zero_at: float | None
    task_done: bool


@dataclass(frozen=True)
class IngestReaperPlan:
    restart_series_ids: tuple[str, ...]
    stop_series_ids: tuple[str, ...]
    drop_series_ids: tuple[str, ...]


def plan_ingest_reaper(
    *,
    jobs: Iterable[IngestReaperJobState],
    now: float,
    idle_ttl_s: float,
    is_pinned_whitelist: Callable[[str], bool],
) -> IngestReaperPlan:
    restart_series_ids: list[str] = []
    stop_series_ids: list[str] = []
    drop_series_ids: list[str] = []
    ttl_s = max(0.0, float(idle_ttl_s))

    for job in jobs:
        series_id = str(job.series_id)
        pinned = bool(is_pinned_whitelist(series_id))

        if bool(job.task_done):
            if pinned or int(job.refcount) > 0:
                restart_series_ids.append(series_id)
            else:
                drop_series_ids.append(series_id)
            continue

        if pinned:
            continue
        if int(job.refcount) != 0 or job.last_zero_at is None:
            continue
        if float(now) - float(job.last_zero_at) < ttl_s:
            continue

        stop_series_ids.append(series_id)
        drop_series_ids.append(series_id)

    return IngestReaperPlan(
        restart_series_ids=tuple(restart_series_ids),
        stop_series_ids=tuple(stop_series_ids),
        drop_series_ids=tuple(drop_series_ids),
    )
