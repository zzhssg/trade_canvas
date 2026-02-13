from __future__ import annotations

from dataclasses import dataclass

from backend.app.ingest_restart_policy import carry_restart_state, mark_restart_failure, plan_ingest_restart


class _FakeGuardrail:
    def __init__(self, *, wait_s: float) -> None:
        self._wait_s = float(wait_s)

    def before_attempt(self) -> float:
        return float(self._wait_s)


@dataclass
class _JobState:
    crashes: int = 0
    last_crash_at: float | None = None


def test_plan_ingest_restart_rejects_when_snapshot_is_stale() -> None:
    plan = plan_ingest_restart(
        current_is_snapshot=False,
        guardrail=None,
    )

    assert plan.should_restart is False
    assert plan.retry_in_s == 0.0


def test_plan_ingest_restart_rejects_when_guardrail_requires_wait() -> None:
    plan = plan_ingest_restart(
        current_is_snapshot=True,
        guardrail=_FakeGuardrail(wait_s=3.0),  # type: ignore[arg-type]
    )

    assert plan.should_restart is False
    assert plan.retry_in_s == 3.0


def test_plan_ingest_restart_allows_when_snapshot_matches_and_no_wait() -> None:
    plan = plan_ingest_restart(
        current_is_snapshot=True,
        guardrail=_FakeGuardrail(wait_s=0.0),  # type: ignore[arg-type]
    )

    assert plan.should_restart is True
    assert plan.retry_in_s == 0.0


def test_mark_restart_failure_updates_crash_state() -> None:
    job = _JobState()

    mark_restart_failure(job=job, at=12.5)

    assert job.crashes == 1
    assert job.last_crash_at == 12.5


def test_carry_restart_state_copies_crash_state() -> None:
    source = _JobState(crashes=3, last_crash_at=21.0)
    target = _JobState(crashes=0, last_crash_at=None)

    carry_restart_state(source=source, target=target)

    assert target.crashes == 3
    assert target.last_crash_at == 21.0
