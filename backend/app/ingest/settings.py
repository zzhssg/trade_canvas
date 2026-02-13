from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhitelistIngestSettings:
    grace_window_s: int = 5
    poll_interval_s: float = 1.0
    batch_limit: int = 1000
    bootstrap_backfill_count: int = 2000
