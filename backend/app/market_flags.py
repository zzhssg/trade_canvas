from __future__ import annotations

import os


_TRUE_SET = {"1", "true", "yes", "on"}


def env_bool(name: str, *, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in _TRUE_SET


def env_int(name: str, *, default: int, minimum: int | None = None) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else int(default)
    except ValueError:
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    return value


def debug_api_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_DEBUG_API")


def market_auto_tail_backfill_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL")


def market_auto_tail_backfill_max_candles(*, fallback: int) -> int:
    return env_int(
        "TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES",
        default=int(fallback),
        minimum=1,
    )


def market_gap_backfill_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL")


def market_gap_backfill_freqtrade_limit(*, fallback: int = 2000) -> int:
    return env_int(
        "TRADE_CANVAS_MARKET_GAP_BACKFILL_FREQTRADE_LIMIT",
        default=int(fallback),
        minimum=1,
    )


def ccxt_backfill_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_CCXT_BACKFILL")


def market_history_source() -> str:
    return (os.environ.get("TRADE_CANVAS_MARKET_HISTORY_SOURCE") or "").strip().lower()


def ondemand_ingest_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST")


def whitelist_ingest_enabled() -> bool:
    return env_bool("TRADE_CANVAS_ENABLE_WHITELIST_INGEST")


def ondemand_idle_ttl_seconds(*, fallback: int = 60) -> int:
    return env_int("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", default=int(fallback), minimum=1)


def ondemand_max_jobs(*, fallback: int = 0) -> int:
    return env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", default=int(fallback), minimum=0)


def derived_backfill_base_candles(*, fallback: int = 2000) -> int:
    return env_int(
        "TRADE_CANVAS_DERIVED_BACKFILL_BASE_CANDLES",
        default=int(fallback),
        minimum=100,
    )
