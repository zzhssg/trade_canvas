from __future__ import annotations

from backend.app.build.job_manager import BuildJobManager


def test_build_job_manager_ensure_is_idempotent() -> None:
    manager = BuildJobManager()
    created_job, created = manager.ensure(job_id="job-1", cache_key="cache-1")
    assert created is True
    assert created_job.status == "building"

    existing_job, created_again = manager.ensure(job_id="job-1", cache_key="cache-1")
    assert created_again is False
    assert existing_job.job_id == "job-1"
    assert existing_job.cache_key == "cache-1"
    assert existing_job.status == "building"


def test_build_job_manager_tracks_terminal_state() -> None:
    manager = BuildJobManager()
    manager.ensure(job_id="job-2", cache_key="cache-2")

    manager.mark_done(job_id="job-2")
    done_job = manager.get("job-2")
    assert done_job is not None
    assert done_job.status == "done"
    assert done_job.finished_at_ms is not None
    assert done_job.error is None

    manager.mark_error(job_id="job-2", error="boom")
    error_job = manager.get("job-2")
    assert error_job is not None
    assert error_job.status == "error"
    assert error_job.error == "boom"
    assert error_job.finished_at_ms is not None
