from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol


class IngestCapacityJobView(Protocol):
    series_id: str
    refcount: int
    last_zero_at: float | None


@dataclass(frozen=True)
class IngestCapacityPlan:
    accepted: bool
    victim_series_id: str | None = None


def plan_ondemand_capacity(
    *,
    jobs: Iterable[IngestCapacityJobView],
    max_jobs: int,
    is_pinned_whitelist: Callable[[str], bool],
    now: float,
) -> IngestCapacityPlan:
    capacity = max(0, int(max_jobs))
    if capacity <= 0:
        return IngestCapacityPlan(accepted=True)

    ondemand_jobs = [job for job in jobs if not is_pinned_whitelist(job.series_id)]
    if len(ondemand_jobs) < capacity:
        return IngestCapacityPlan(accepted=True)

    idle_jobs = [job for job in ondemand_jobs if int(job.refcount) == 0 and job.last_zero_at is not None]
    if not idle_jobs:
        return IngestCapacityPlan(accepted=False)

    victim = min(idle_jobs, key=lambda job: float(job.last_zero_at or now))
    return IngestCapacityPlan(
        accepted=True,
        victim_series_id=str(victim.series_id),
    )
