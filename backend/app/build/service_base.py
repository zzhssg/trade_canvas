from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from .job_manager import BuildJob, BuildJobManager


@dataclass(frozen=True)
class BuildReservation:
    status: str
    job_id: str
    cache_key: str
    created: bool


class PackageBuildServiceBase:
    def __init__(self) -> None:
        self._build_jobs = BuildJobManager()

    def _reserve_build_job(
        self,
        *,
        cache_key: str,
        cache_exists: Callable[[str], bool],
    ) -> BuildReservation:
        normalized_cache_key = str(cache_key)
        job_id = str(normalized_cache_key)
        if cache_exists(normalized_cache_key):
            return BuildReservation(
                status="done",
                job_id=job_id,
                cache_key=normalized_cache_key,
                created=False,
            )
        existing, created = self._build_jobs.ensure(
            job_id=job_id,
            cache_key=normalized_cache_key,
        )
        return BuildReservation(
            status=str(existing.status),
            job_id=str(existing.job_id),
            cache_key=str(existing.cache_key),
            created=bool(created),
        )

    def _resolve_build_status(
        self,
        *,
        job_id: str,
        cache_exists: Callable[[str], bool],
    ) -> tuple[str, BuildJob | None]:
        normalized_job_id = str(job_id)
        job = self._build_jobs.get(normalized_job_id)
        if job is None:
            if cache_exists(normalized_job_id):
                return ("done", None)
            return ("build_required", None)
        status = str(job.status)
        if status == "error":
            return ("error", job)
        if status == "done":
            return ("done", job)
        return ("building", job)

    def _start_tracked_build(
        self,
        *,
        job_id: str,
        thread_name: str,
        build_fn: Callable[[], None],
    ) -> None:
        normalized_job_id = str(job_id)

        def runner() -> None:
            try:
                build_fn()
                self._build_jobs.mark_done(job_id=normalized_job_id)
            except Exception as exc:
                self._build_jobs.mark_error(job_id=normalized_job_id, error=str(exc))

        threading.Thread(
            target=runner,
            name=str(thread_name),
            daemon=True,
        ).start()
