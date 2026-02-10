from __future__ import annotations

from dataclasses import dataclass

from .flags import FeatureFlags, env_bool, env_int


@dataclass(frozen=True)
class RuntimeFlags:
    enable_debug_api: bool
    enable_market_auto_tail_backfill: bool
    market_auto_tail_backfill_max_candles: int | None
    enable_market_gap_backfill: bool
    market_gap_backfill_freqtrade_limit: int
    enable_ccxt_backfill: bool
    enable_ccxt_backfill_on_read: bool
    ondemand_max_jobs: int
    enable_kline_health_v2: bool
    kline_health_backfill_recent_seconds: int
    backtest_require_trades: bool
    freqtrade_mock_enabled: bool


def load_runtime_flags(*, base_flags: FeatureFlags) -> RuntimeFlags:
    return RuntimeFlags(
        enable_debug_api=bool(base_flags.enable_debug_api),
        enable_market_auto_tail_backfill=bool(base_flags.enable_market_auto_tail_backfill),
        market_auto_tail_backfill_max_candles=base_flags.market_auto_tail_backfill_max_candles,
        enable_market_gap_backfill=env_bool("TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL"),
        market_gap_backfill_freqtrade_limit=env_int(
            "TRADE_CANVAS_MARKET_GAP_BACKFILL_FREQTRADE_LIMIT",
            default=2000,
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
    )
