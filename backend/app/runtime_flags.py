from __future__ import annotations

import os
from dataclasses import dataclass

from .derived_timeframes import DEFAULT_DERIVED_TIMEFRAMES, normalize_derived_timeframes
from .flags import FeatureFlags, env_bool, env_int, resolve_env_float, resolve_env_str


def _env_csv(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return tuple(default)
    return normalize_derived_timeframes(part.strip() for part in raw.split(","))


@dataclass(frozen=True)
class RuntimeFlags:
    enable_debug_api: bool
    enable_factor_ingest: bool
    enable_factor_fingerprint_rebuild: bool
    factor_pivot_window_major: int
    factor_pivot_window_minor: int
    factor_lookback_candles: int
    factor_state_rebuild_event_limit: int
    factor_rebuild_keep_candles: int
    factor_logic_version_override: str
    enable_overlay_ingest: bool
    overlay_window_candles: int
    enable_ingest_compensate_overlay_error: bool
    enable_ingest_compensate_new_candles: bool
    enable_market_auto_tail_backfill: bool
    market_auto_tail_backfill_max_candles: int | None
    enable_market_gap_backfill: bool
    market_gap_backfill_freqtrade_limit: int
    enable_startup_kline_sync: bool
    startup_kline_sync_target_candles: int
    ccxt_timeout_ms: int
    blocking_workers: int
    enable_ccxt_backfill: bool
    enable_ccxt_backfill_on_read: bool
    ondemand_max_jobs: int
    enable_kline_health_v2: bool
    kline_health_backfill_recent_seconds: int
    backtest_require_trades: bool
    freqtrade_mock_enabled: bool
    enable_replay_v1: bool
    enable_replay_ensure_coverage: bool
    enable_replay_package: bool
    market_history_source: str
    enable_derived_timeframes: bool
    derived_base_timeframe: str
    derived_timeframes: tuple[str, ...]
    derived_backfill_base_candles: int
    binance_ws_batch_max: int
    binance_ws_flush_s: float
    market_forming_min_interval_ms: int


def load_runtime_flags(*, base_flags: FeatureFlags) -> RuntimeFlags:
    return RuntimeFlags(
        enable_debug_api=bool(base_flags.enable_debug_api),
        enable_factor_ingest=env_bool("TRADE_CANVAS_ENABLE_FACTOR_INGEST", default=True),
        enable_factor_fingerprint_rebuild=env_bool("TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD", default=True),
        factor_pivot_window_major=env_int(
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            default=50,
            minimum=1,
        ),
        factor_pivot_window_minor=env_int(
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            default=5,
            minimum=1,
        ),
        factor_lookback_candles=env_int(
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            default=20000,
            minimum=100,
        ),
        factor_state_rebuild_event_limit=env_int(
            "TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT",
            default=50000,
            minimum=1000,
        ),
        factor_rebuild_keep_candles=env_int(
            "TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES",
            default=2000,
            minimum=100,
        ),
        factor_logic_version_override=resolve_env_str("TRADE_CANVAS_FACTOR_LOGIC_VERSION"),
        enable_overlay_ingest=env_bool("TRADE_CANVAS_ENABLE_OVERLAY_INGEST", default=True),
        overlay_window_candles=env_int(
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
            default=2000,
            minimum=100,
        ),
        enable_ingest_compensate_overlay_error=env_bool("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_OVERLAY_ERROR"),
        enable_ingest_compensate_new_candles=env_bool("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_NEW_CANDLES"),
        enable_market_auto_tail_backfill=bool(base_flags.enable_market_auto_tail_backfill),
        market_auto_tail_backfill_max_candles=base_flags.market_auto_tail_backfill_max_candles,
        enable_market_gap_backfill=env_bool("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL"),
        market_gap_backfill_freqtrade_limit=env_int(
            "TRADE_CANVAS_MARKET_GAP_BACKFILL_FREQTRADE_LIMIT",
            default=2000,
            minimum=1,
        ),
        enable_startup_kline_sync=env_bool("TRADE_CANVAS_ENABLE_STARTUP_KLINE_SYNC", default=False),
        startup_kline_sync_target_candles=env_int(
            "TRADE_CANVAS_STARTUP_KLINE_SYNC_TARGET_CANDLES",
            default=2000,
            minimum=100,
        ),
        ccxt_timeout_ms=env_int(
            "TRADE_CANVAS_CCXT_TIMEOUT_MS",
            default=10_000,
            minimum=1000,
        ),
        blocking_workers=env_int(
            "TRADE_CANVAS_BLOCKING_WORKERS",
            default=8,
            minimum=1,
        ),
        enable_ccxt_backfill=env_bool("TRADE_CANVAS_ENABLE_CCXT_BACKFILL"),
        enable_ccxt_backfill_on_read=env_bool(
            "TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ",
            default=bool(base_flags.enable_market_auto_tail_backfill),
        ),
        ondemand_max_jobs=env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", default=0, minimum=0),
        enable_kline_health_v2=env_bool("TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2"),
        kline_health_backfill_recent_seconds=env_int(
            "TRADE_CANVAS_KLINE_HEALTH_BACKFILL_RECENT_SECONDS",
            default=120,
            minimum=5,
        ),
        backtest_require_trades=env_bool("TRADE_CANVAS_BACKTEST_REQUIRE_TRADES"),
        freqtrade_mock_enabled=env_bool("TRADE_CANVAS_FREQTRADE_MOCK"),
        enable_replay_v1=env_bool("TRADE_CANVAS_ENABLE_REPLAY_V1"),
        enable_replay_ensure_coverage=env_bool("TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE"),
        enable_replay_package=env_bool("TRADE_CANVAS_ENABLE_REPLAY_PACKAGE"),
        market_history_source=resolve_env_str("TRADE_CANVAS_MARKET_HISTORY_SOURCE", fallback="").lower(),
        enable_derived_timeframes=env_bool("TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES"),
        derived_base_timeframe=resolve_env_str("TRADE_CANVAS_DERIVED_BASE_TIMEFRAME", fallback="1m") or "1m",
        derived_timeframes=_env_csv(
            "TRADE_CANVAS_DERIVED_TIMEFRAMES",
            default=DEFAULT_DERIVED_TIMEFRAMES,
        ),
        derived_backfill_base_candles=env_int(
            "TRADE_CANVAS_DERIVED_BACKFILL_BASE_CANDLES",
            default=2000,
            minimum=100,
        ),
        binance_ws_batch_max=env_int(
            "TRADE_CANVAS_BINANCE_WS_BATCH_MAX",
            default=200,
            minimum=1,
        ),
        binance_ws_flush_s=resolve_env_float(
            "TRADE_CANVAS_BINANCE_WS_FLUSH_S",
            fallback=0.5,
            minimum=0.05,
        ),
        market_forming_min_interval_ms=env_int(
            "TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS",
            default=250,
            minimum=0,
        ),
    )
