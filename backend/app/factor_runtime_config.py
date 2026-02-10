from __future__ import annotations

import os
from dataclasses import dataclass


def truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000
    state_rebuild_event_limit: int = 50000


def factor_ingest_enabled() -> bool:
    raw = os.environ.get("TRADE_CANVAS_ENABLE_FACTOR_INGEST", "1")
    return truthy_flag(raw)


def factor_fingerprint_rebuild_enabled() -> bool:
    raw = os.environ.get("TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD", "1")
    return truthy_flag(raw)


def factor_logic_version_override() -> str:
    return str(os.environ.get("TRADE_CANVAS_FACTOR_LOGIC_VERSION") or "")


def factor_rebuild_keep_candles(*, fallback: int = 2000, minimum: int = 100) -> int:
    raw = (os.environ.get("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES") or "").strip()
    if not raw:
        return int(max(int(minimum), int(fallback)))
    try:
        parsed = int(raw)
    except ValueError:
        return int(max(int(minimum), int(fallback)))
    return int(max(int(minimum), parsed))


def load_factor_settings(*, defaults: FactorSettings) -> FactorSettings:
    major_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MAJOR") or "").strip()
    minor_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MINOR") or "").strip()
    lookback_raw = (os.environ.get("TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES") or "").strip()
    state_limit_raw = (os.environ.get("TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT") or "").strip()

    major = defaults.pivot_window_major
    minor = defaults.pivot_window_minor
    lookback = defaults.lookback_candles
    state_limit = defaults.state_rebuild_event_limit

    if major_raw:
        try:
            major = max(1, int(major_raw))
        except ValueError:
            major = defaults.pivot_window_major
    if minor_raw:
        try:
            minor = max(1, int(minor_raw))
        except ValueError:
            minor = defaults.pivot_window_minor
    if lookback_raw:
        try:
            lookback = max(100, int(lookback_raw))
        except ValueError:
            lookback = defaults.lookback_candles
    if state_limit_raw:
        try:
            state_limit = max(1000, int(state_limit_raw))
        except ValueError:
            state_limit = defaults.state_rebuild_event_limit

    return FactorSettings(
        pivot_window_major=int(major),
        pivot_window_minor=int(minor),
        lookback_candles=int(lookback),
        state_rebuild_event_limit=int(state_limit),
    )
