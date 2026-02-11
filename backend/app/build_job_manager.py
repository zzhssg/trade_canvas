from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildJob:
    job_id: str
    cache_key: str
    status: str
    started_at_ms: int
    finished_at_ms: int | None = None
    error: str | None = None


@dataclass
class _BuildJobState:
    job_id: str
    cache_key: str
    status: str
    started_at_ms: int
    finished_at_ms: int | None = None
    error: str | None = None

    def to_view(self) -> BuildJob:
        return BuildJob(
            job_id=self.job_id,
            cache_key=self.cache_key,
            status=self.status,
            started_at_ms=self.started_at_ms,
            finished_at_ms=self.finished_at_ms,
            error=self.error,
        )


class BuildJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, _BuildJobState] = {}

    def get(self, job_id: str) -> BuildJob | None:
        with self._lock:
            state = self._jobs.get(str(job_id))
            return state.to_view() if state is not None else None

    def ensure(self, *, job_id: str, cache_key: str) -> tuple[BuildJob, bool]:
        normalized_job_id = str(job_id)
        normalized_cache_key = str(cache_key)
        now_ms = int(time.time() * 1000)
        with self._lock:
            existing = self._jobs.get(normalized_job_id)
            if existing is not None:
                return (existing.to_view(), False)
            created = _BuildJobState(
                job_id=normalized_job_id,
                cache_key=normalized_cache_key,
                status="building",
                started_at_ms=now_ms,
            )
            self._jobs[normalized_job_id] = created
            return (created.to_view(), True)

    def mark_done(self, *, job_id: str) -> None:
        with self._lock:
            state = self._jobs.get(str(job_id))
            if state is None:
                return
            state.status = "done"
            state.error = None
            state.finished_at_ms = int(time.time() * 1000)

    def mark_error(self, *, job_id: str, error: str) -> None:
        with self._lock:
            state = self._jobs.get(str(job_id))
            if state is None:
                return
            state.status = "error"
            state.error = str(error)
            state.finished_at_ms = int(time.time() * 1000)
