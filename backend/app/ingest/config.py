from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestRuntimeConfig:
    """Aggregated config for IngestSupervisor and related ingest components."""

    derived_enabled: bool = False
    derived_base_timeframe: str = "1m"
    derived_timeframes: tuple[str, ...] = ()
    derived_backfill_base_candles: int = 2000
    ws_batch_max: int = 200
    ws_flush_s: float = 0.5
    forming_min_interval_ms: int = 250
    loop_guardrail_enabled: bool = False
    guardrail_crash_budget: int = 5
    guardrail_budget_window_s: float = 60.0
    guardrail_backoff_initial_s: float = 1.0
    guardrail_backoff_max_s: float = 15.0
    guardrail_open_cooldown_s: float = 30.0
    role_guard_enabled: bool = False
    ingest_role: str = "hybrid"
    ondemand_max_jobs: int = 0
    market_history_source: str = ""
