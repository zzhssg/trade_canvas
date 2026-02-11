from __future__ import annotations

from backend.app.ingest_loop_guardrail import IngestLoopGuardrail, IngestLoopGuardrailConfig


def test_guardrail_opens_when_crash_budget_exhausted() -> None:
    guardrail = IngestLoopGuardrail(
        enabled=True,
        config=IngestLoopGuardrailConfig(
            crash_budget=2,
            budget_window_s=60.0,
            backoff_initial_s=0.1,
            backoff_max_s=1.0,
            open_cooldown_s=5.0,
        ),
    )

    delay1 = guardrail.on_failure(error=RuntimeError("boom-1"), now=10.0)
    delay2 = guardrail.on_failure(error=RuntimeError("boom-2"), now=11.0)
    snapshot = guardrail.snapshot(now=11.0)

    assert delay1 == 0.1
    assert delay2 == 5.0
    assert snapshot["state"] == "open"
    assert float(snapshot["next_retry_in_s"]) > 0


def test_guardrail_half_open_and_success_resets_state() -> None:
    guardrail = IngestLoopGuardrail(
        enabled=True,
        config=IngestLoopGuardrailConfig(
            crash_budget=1,
            budget_window_s=60.0,
            backoff_initial_s=0.1,
            backoff_max_s=1.0,
            open_cooldown_s=2.0,
        ),
    )
    guardrail.on_failure(error=RuntimeError("boom"), now=20.0)
    assert guardrail.before_attempt(now=21.0) == 1.0
    assert guardrail.before_attempt(now=22.1) == 0.0
    half_open_snapshot = guardrail.snapshot(now=22.1)
    assert half_open_snapshot["state"] == "half_open"

    guardrail.on_success(now=22.2)
    closed_snapshot = guardrail.snapshot(now=22.2)
    assert closed_snapshot["state"] == "closed"
    assert closed_snapshot["window_failures"] == 0
