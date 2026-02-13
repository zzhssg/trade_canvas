from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiGateConfig:
    """Runtime gate flags consumed by HTTP route handlers."""

    debug_api: bool = False
    dev_api: bool = False
    read_repair_api: bool = False
    kline_health_v2: bool = False
    kline_health_backfill_recent_seconds: int = 120
    runtime_metrics: bool = False
    capacity_metrics: bool = False
