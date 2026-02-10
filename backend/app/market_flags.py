from __future__ import annotations

from .flags import resolve_env_bool, resolve_env_int, resolve_env_str


def debug_api_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_DEBUG_API", fallback=False)


def market_auto_tail_backfill_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL", fallback=False)


def market_auto_tail_backfill_max_candles(*, fallback: int) -> int:
    return resolve_env_int(
        "TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES",
        fallback=int(fallback),
        minimum=1,
    )


def market_gap_backfill_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL", fallback=False)


def market_gap_backfill_freqtrade_limit(*, fallback: int = 2000) -> int:
    return resolve_env_int(
        "TRADE_CANVAS_MARKET_GAP_BACKFILL_FREQTRADE_LIMIT",
        fallback=int(fallback),
        minimum=1,
    )


def ccxt_backfill_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_CCXT_BACKFILL", fallback=False)


def ccxt_backfill_on_read_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", fallback=False)


def market_history_source() -> str:
    return resolve_env_str("TRADE_CANVAS_MARKET_HISTORY_SOURCE", fallback="").lower()


def ondemand_ingest_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST", fallback=False)


def whitelist_ingest_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_WHITELIST_INGEST", fallback=False)


def ondemand_idle_ttl_seconds(*, fallback: int = 60) -> int:
    return resolve_env_int("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", fallback=int(fallback), minimum=1)


def ondemand_max_jobs(*, fallback: int = 0) -> int:
    return resolve_env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", fallback=int(fallback), minimum=0)


def derived_backfill_base_candles(*, fallback: int = 2000) -> int:
    return resolve_env_int(
        "TRADE_CANVAS_DERIVED_BACKFILL_BASE_CANDLES",
        fallback=int(fallback),
        minimum=100,
    )
