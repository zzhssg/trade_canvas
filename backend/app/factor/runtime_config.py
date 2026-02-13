from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000
    state_rebuild_event_limit: int = 50000
