from __future__ import annotations

import os
from dataclasses import dataclass


def truthy_flag(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return truthy_flag(raw)


def resolve_env_bool(name: str, *, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(fallback)
    return truthy_flag(raw)


def resolve_env_int(name: str, *, fallback: int, minimum: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(int(minimum), int(fallback))
    try:
        return max(int(minimum), int(raw))
    except ValueError:
        return max(int(minimum), int(fallback))


def resolve_env_float(name: str, *, fallback: float, minimum: float = 0.0) -> float:
    raw = (os.environ.get(name) or "").strip()
    fallback_value = max(float(minimum), float(fallback))
    if not raw:
        return fallback_value
    try:
        return max(float(minimum), float(raw))
    except ValueError:
        return fallback_value


def resolve_env_str(name: str, *, fallback: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return str(fallback).strip()
    return str(raw).strip()


def env_int(name: str, *, default: int, minimum: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(int(minimum), int(default))
    try:
        return max(int(minimum), int(raw))
    except ValueError:
        return max(int(minimum), int(default))


@dataclass(frozen=True)
class FeatureFlags:
    enable_debug_api: bool
    enable_read_strict_mode: bool
    enable_whitelist_ingest: bool
    enable_ondemand_ingest: bool
    enable_market_auto_tail_backfill: bool
    market_auto_tail_backfill_max_candles: int | None
    ondemand_idle_ttl_s: int


def load_feature_flags() -> FeatureFlags:
    max_candles_raw = (os.environ.get("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES") or "").strip()
    max_candles: int | None = None
    if max_candles_raw:
        try:
            parsed = int(max_candles_raw)
            if parsed > 0:
                max_candles = parsed
        except ValueError:
            max_candles = None
    return FeatureFlags(
        enable_debug_api=env_bool("TRADE_CANVAS_ENABLE_DEBUG_API"),
        enable_read_strict_mode=env_bool("TRADE_CANVAS_ENABLE_READ_STRICT_MODE"),
        enable_whitelist_ingest=env_bool("TRADE_CANVAS_ENABLE_WHITELIST_INGEST"),
        enable_ondemand_ingest=env_bool("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"),
        enable_market_auto_tail_backfill=env_bool("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL"),
        market_auto_tail_backfill_max_candles=max_candles,
        ondemand_idle_ttl_s=env_int("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", default=60, minimum=1),
    )
