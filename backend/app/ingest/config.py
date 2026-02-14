from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipelines import IngestPipeline
    from .settings import WhitelistIngestSettings


@dataclass(frozen=True)
class IngestDerivedConfig:
    enabled: bool = False
    base_timeframe: str = "1m"
    timeframes: tuple[str, ...] = ()
    backfill_base_candles: int = 2000


@dataclass(frozen=True)
class IngestWsConfig:
    batch_max: int = 200
    flush_s: float = 0.5
    forming_min_interval_ms: int = 250


@dataclass(frozen=True)
class IngestGuardrailConfig:
    enabled: bool = False
    crash_budget: int = 5
    budget_window_s: float = 60.0
    backoff_initial_s: float = 1.0
    backoff_max_s: float = 15.0
    open_cooldown_s: float = 30.0


@dataclass(frozen=True)
class IngestRoleConfig:
    guard_enabled: bool = False
    ingest_role: str = "hybrid"


@dataclass(frozen=True)
class IngestRuntimeConfig:
    """Aggregated config for IngestSupervisor and related ingest components."""

    derived: IngestDerivedConfig = field(default_factory=IngestDerivedConfig)
    ws: IngestWsConfig = field(default_factory=IngestWsConfig)
    guardrail: IngestGuardrailConfig = field(default_factory=IngestGuardrailConfig)
    role: IngestRoleConfig = field(default_factory=IngestRoleConfig)
    ondemand_max_jobs: int = 0
    market_history_source: str = ""


@dataclass(frozen=True)
class IngestSupervisorInitConfig:
    whitelist_series_ids: tuple[str, ...]
    ingest_settings: WhitelistIngestSettings | None = None
    ondemand_idle_ttl_s: int = 60
    whitelist_ingest_enabled: bool = False
    ingest_pipeline: IngestPipeline | None = None
    runtime: IngestRuntimeConfig = field(default_factory=IngestRuntimeConfig)
