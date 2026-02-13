from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .ingest_loop_guardrail import IngestLoopGuardrail


class IngestRestartJobState(Protocol):
    crashes: int
    last_crash_at: float | None


@dataclass(frozen=True)
class IngestRestartPlan:
    should_restart: bool
    retry_in_s: float = 0.0


def plan_ingest_restart(
    *,
    current_is_snapshot: bool,
    guardrail: IngestLoopGuardrail | None,
) -> IngestRestartPlan:
    if not bool(current_is_snapshot):
        return IngestRestartPlan(should_restart=False)
    if guardrail is None:
        return IngestRestartPlan(should_restart=True)

    wait_s = float(guardrail.before_attempt())
    if wait_s > 0:
        return IngestRestartPlan(
            should_restart=False,
            retry_in_s=wait_s,
        )
    return IngestRestartPlan(should_restart=True)


def mark_restart_failure(*, job: IngestRestartJobState, at: float) -> None:
    job.crashes += 1
    job.last_crash_at = float(at)


def carry_restart_state(
    *,
    source: IngestRestartJobState,
    target: IngestRestartJobState,
) -> None:
    target.crashes = int(source.crashes)
    target.last_crash_at = source.last_crash_at
