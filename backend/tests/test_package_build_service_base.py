from __future__ import annotations

import time

from backend.app.package_build_service_base import PackageBuildServiceBase


class _Harness(PackageBuildServiceBase):
    def __init__(self) -> None:
        super().__init__()
        self._cache_keys: set[str] = set()

    def cache_exists(self, cache_key: str) -> bool:
        return str(cache_key) in self._cache_keys

    def mark_cache(self, cache_key: str) -> None:
        self._cache_keys.add(str(cache_key))


def _wait_for_status(harness: _Harness, *, job_id: str, expected: str, timeout_s: float = 1.0) -> None:
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        status, _ = harness._resolve_build_status(job_id=job_id, cache_exists=harness.cache_exists)
        if status == expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"status_timeout: expected={expected} job_id={job_id}")


def test_reserve_build_job_returns_done_when_cache_exists() -> None:
    harness = _Harness()
    harness.mark_cache("abc")

    reservation = harness._reserve_build_job(cache_key="abc", cache_exists=harness.cache_exists)

    assert reservation.status == "done"
    assert reservation.job_id == "abc"
    assert reservation.cache_key == "abc"
    assert reservation.created is False


def test_reserve_build_job_returns_existing_status_when_job_already_present() -> None:
    harness = _Harness()

    first = harness._reserve_build_job(cache_key="abc", cache_exists=harness.cache_exists)
    second = harness._reserve_build_job(cache_key="abc", cache_exists=harness.cache_exists)

    assert first.status == "building"
    assert first.created is True
    assert second.status == "building"
    assert second.created is False


def test_resolve_build_status_uses_cache_fallback_when_job_missing() -> None:
    harness = _Harness()

    missing_status, missing_job = harness._resolve_build_status(job_id="abc", cache_exists=harness.cache_exists)
    assert missing_status == "build_required"
    assert missing_job is None

    harness.mark_cache("abc")
    cached_status, cached_job = harness._resolve_build_status(job_id="abc", cache_exists=harness.cache_exists)
    assert cached_status == "done"
    assert cached_job is None


def test_start_tracked_build_marks_job_done() -> None:
    harness = _Harness()
    reservation = harness._reserve_build_job(cache_key="abc", cache_exists=harness.cache_exists)
    assert reservation.created is True

    harness._start_tracked_build(
        job_id=reservation.job_id,
        thread_name="test-build-done",
        build_fn=lambda: None,
    )
    _wait_for_status(harness, job_id=reservation.job_id, expected="done")


def test_start_tracked_build_marks_job_error() -> None:
    harness = _Harness()
    reservation = harness._reserve_build_job(cache_key="abc", cache_exists=harness.cache_exists)
    assert reservation.created is True

    def _raise() -> None:
        raise RuntimeError("boom")

    harness._start_tracked_build(
        job_id=reservation.job_id,
        thread_name="test-build-error",
        build_fn=_raise,
    )
    _wait_for_status(harness, job_id=reservation.job_id, expected="error")
    _, job = harness._resolve_build_status(job_id=reservation.job_id, cache_exists=harness.cache_exists)
    assert job is not None
    assert job.error == "boom"
