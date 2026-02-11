from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Literal


CircuitState = Literal["closed", "open", "half_open"]


@dataclass(frozen=True)
class IngestLoopGuardrailConfig:
    crash_budget: int = 5
    budget_window_s: float = 60.0
    backoff_initial_s: float = 1.0
    backoff_max_s: float = 15.0
    open_cooldown_s: float = 30.0


class IngestLoopGuardrail:
    def __init__(
        self,
        *,
        enabled: bool,
        config: IngestLoopGuardrailConfig | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._config = config or IngestLoopGuardrailConfig()
        self._state: CircuitState = "closed"
        self._failures: Deque[float] = deque()
        self._consecutive_failures = 0
        self._last_failure_at: float | None = None
        self._last_error: str | None = None
        self._open_until: float | None = None
        self._last_backoff_s = 0.0

    def _now(self, now: float | None = None) -> float:
        if now is None:
            return float(time.monotonic())
        return float(now)

    def _trim_failures(self, now: float) -> None:
        window_s = max(1.0, float(self._config.budget_window_s))
        cutoff = float(now - window_s)
        while self._failures and float(self._failures[0]) < cutoff:
            self._failures.popleft()

    def before_attempt(self, *, now: float | None = None) -> float:
        if not self._enabled:
            return 0.0
        current = self._now(now)
        if self._state != "open":
            return 0.0
        open_until = self._open_until
        if open_until is None:
            self._state = "half_open"
            return 0.0
        if current >= float(open_until):
            self._state = "half_open"
            self._open_until = None
            return 0.0
        return max(0.0, float(open_until) - float(current))

    def on_success(self, *, now: float | None = None) -> None:
        if not self._enabled:
            return
        _ = self._now(now)
        self._state = "closed"
        self._failures.clear()
        self._consecutive_failures = 0
        self._last_backoff_s = 0.0
        self._open_until = None

    def on_failure(self, *, error: Exception, now: float | None = None) -> float:
        if not self._enabled:
            return 0.0
        current = self._now(now)
        self._failures.append(float(current))
        self._trim_failures(current)
        self._consecutive_failures += 1
        self._last_failure_at = float(current)
        self._last_error = str(error)

        crash_budget = max(1, int(self._config.crash_budget))
        if len(self._failures) >= crash_budget:
            cooldown = max(0.0, float(self._config.open_cooldown_s))
            self._state = "open"
            self._open_until = float(current + cooldown)
            self._last_backoff_s = float(cooldown)
            return float(cooldown)

        if self._state == "half_open":
            cooldown = max(0.0, float(self._config.open_cooldown_s))
            self._state = "open"
            self._open_until = float(current + cooldown)
            self._last_backoff_s = float(cooldown)
            return float(cooldown)

        backoff = min(
            max(0.0, float(self._config.backoff_max_s)),
            max(0.0, float(self._config.backoff_initial_s)) * (2 ** max(0, self._consecutive_failures - 1)),
        )
        self._state = "closed"
        self._last_backoff_s = float(backoff)
        return float(backoff)

    def snapshot(self, *, now: float | None = None) -> dict[str, object]:
        current = self._now(now)
        self._trim_failures(current)
        next_retry_in_s = 0.0
        if self._state == "open" and self._open_until is not None:
            next_retry_in_s = max(0.0, float(self._open_until) - float(current))
        return {
            "enabled": bool(self._enabled),
            "state": str(self._state),
            "window_failures": int(len(self._failures)),
            "consecutive_failures": int(self._consecutive_failures),
            "last_failure_at": self._last_failure_at,
            "last_error": self._last_error,
            "last_backoff_s": float(self._last_backoff_s),
            "next_retry_in_s": float(next_retry_in_s),
            "config": {
                "crash_budget": int(self._config.crash_budget),
                "budget_window_s": float(self._config.budget_window_s),
                "backoff_initial_s": float(self._config.backoff_initial_s),
                "backoff_max_s": float(self._config.backoff_max_s),
                "open_cooldown_s": float(self._config.open_cooldown_s),
            },
        }
