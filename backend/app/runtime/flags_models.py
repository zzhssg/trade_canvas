from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class RuntimeApiFlags:
    enable_debug_api: bool
    enable_dev_api: bool
    enable_runtime_metrics: bool
    enable_capacity_metrics: bool
    enable_read_ledger_warmup: bool
    enable_kline_health_v2: bool
    enable_read_repair_api: bool
    kline_health_backfill_recent_seconds: int


@dataclass(frozen=True)
class RuntimeScaleoutFlags:
    enable_pg_store: bool
    enable_pg_only: bool
    enable_ws_pubsub: bool


@dataclass(frozen=True)
class RuntimeFactorFlags:
    enable_factor_ingest: bool
    enable_factor_fingerprint_rebuild: bool
    pivot_window_major: int
    pivot_window_minor: int
    lookback_candles: int
    state_rebuild_event_limit: int
    rebuild_keep_candles: int
    logic_version_override: str


@dataclass(frozen=True)
class RuntimeOverlayFlags:
    enable_overlay_ingest: bool
    window_candles: int


@dataclass(frozen=True)
class RuntimeFeatureFlags:
    enable_feature_ingest: bool
    enable_feature_strict_read: bool


@dataclass(frozen=True)
class RuntimeIngestFlags:
    enable_ingest_role_guard: bool
    ingest_role: str
    enable_ingest_compensate_overlay_error: bool
    enable_ingest_compensate_new_candles: bool
    enable_ingest_loop_guardrail: bool
    enable_whitelist_ingest: bool
    enable_ondemand_ingest: bool
    ondemand_idle_ttl_s: int
    ondemand_max_jobs: int
    binance_ws_batch_max: int
    binance_ws_flush_s: float
    market_forming_min_interval_ms: int


@dataclass(frozen=True)
class RuntimeMarketFlags:
    enable_market_auto_tail_backfill: bool
    enable_strict_closed_only: bool
    market_auto_tail_backfill_max_candles: int | None
    enable_market_backfill_progress_persistence: bool
    enable_market_gap_backfill: bool
    market_gap_backfill_freqtrade_limit: int
    enable_startup_kline_sync: bool
    startup_kline_sync_target_candles: int
    ccxt_timeout_ms: int
    enable_ccxt_backfill: bool
    enable_ccxt_backfill_on_read: bool
    market_history_source: str


@dataclass(frozen=True)
class RuntimeDerivedFlags:
    enable_derived_timeframes: bool
    derived_base_timeframe: str
    derived_timeframes: tuple[str, ...]
    derived_backfill_base_candles: int


@dataclass(frozen=True)
class RuntimeReplayFlags:
    enable_replay_v1: bool
    enable_replay_ensure_coverage: bool


@dataclass(frozen=True)
class RuntimeExecutionFlags:
    blocking_workers: int
    backtest_require_trades: bool
    freqtrade_mock_enabled: bool


@dataclass(frozen=True)
class RuntimeFlags:
    api: RuntimeApiFlags
    scaleout: RuntimeScaleoutFlags
    factor: RuntimeFactorFlags
    overlay: RuntimeOverlayFlags
    feature: RuntimeFeatureFlags
    ingest: RuntimeIngestFlags
    market: RuntimeMarketFlags
    derived: RuntimeDerivedFlags
    replay: RuntimeReplayFlags
    execution: RuntimeExecutionFlags

    _ALIASES: ClassVar[dict[str, tuple[str, str]]] = {
        "enable_debug_api": ("api", "enable_debug_api"),
        "enable_dev_api": ("api", "enable_dev_api"),
        "enable_runtime_metrics": ("api", "enable_runtime_metrics"),
        "enable_capacity_metrics": ("api", "enable_capacity_metrics"),
        "enable_read_ledger_warmup": ("api", "enable_read_ledger_warmup"),
        "enable_kline_health_v2": ("api", "enable_kline_health_v2"),
        "enable_read_repair_api": ("api", "enable_read_repair_api"),
        "kline_health_backfill_recent_seconds": ("api", "kline_health_backfill_recent_seconds"),
        "enable_pg_store": ("scaleout", "enable_pg_store"),
        "enable_pg_only": ("scaleout", "enable_pg_only"),
        "enable_ws_pubsub": ("scaleout", "enable_ws_pubsub"),
        "enable_factor_ingest": ("factor", "enable_factor_ingest"),
        "enable_factor_fingerprint_rebuild": ("factor", "enable_factor_fingerprint_rebuild"),
        "factor_pivot_window_major": ("factor", "pivot_window_major"),
        "factor_pivot_window_minor": ("factor", "pivot_window_minor"),
        "factor_lookback_candles": ("factor", "lookback_candles"),
        "factor_state_rebuild_event_limit": ("factor", "state_rebuild_event_limit"),
        "factor_rebuild_keep_candles": ("factor", "rebuild_keep_candles"),
        "factor_logic_version_override": ("factor", "logic_version_override"),
        "enable_overlay_ingest": ("overlay", "enable_overlay_ingest"),
        "overlay_window_candles": ("overlay", "window_candles"),
        "enable_feature_ingest": ("feature", "enable_feature_ingest"),
        "enable_feature_strict_read": ("feature", "enable_feature_strict_read"),
        "enable_ingest_role_guard": ("ingest", "enable_ingest_role_guard"),
        "ingest_role": ("ingest", "ingest_role"),
        "enable_ingest_compensate_overlay_error": ("ingest", "enable_ingest_compensate_overlay_error"),
        "enable_ingest_compensate_new_candles": ("ingest", "enable_ingest_compensate_new_candles"),
        "enable_ingest_loop_guardrail": ("ingest", "enable_ingest_loop_guardrail"),
        "enable_whitelist_ingest": ("ingest", "enable_whitelist_ingest"),
        "enable_ondemand_ingest": ("ingest", "enable_ondemand_ingest"),
        "ondemand_idle_ttl_s": ("ingest", "ondemand_idle_ttl_s"),
        "ondemand_max_jobs": ("ingest", "ondemand_max_jobs"),
        "binance_ws_batch_max": ("ingest", "binance_ws_batch_max"),
        "binance_ws_flush_s": ("ingest", "binance_ws_flush_s"),
        "market_forming_min_interval_ms": ("ingest", "market_forming_min_interval_ms"),
        "enable_market_auto_tail_backfill": ("market", "enable_market_auto_tail_backfill"),
        "enable_strict_closed_only": ("market", "enable_strict_closed_only"),
        "market_auto_tail_backfill_max_candles": ("market", "market_auto_tail_backfill_max_candles"),
        "enable_market_backfill_progress_persistence": ("market", "enable_market_backfill_progress_persistence"),
        "enable_market_gap_backfill": ("market", "enable_market_gap_backfill"),
        "market_gap_backfill_freqtrade_limit": ("market", "market_gap_backfill_freqtrade_limit"),
        "enable_startup_kline_sync": ("market", "enable_startup_kline_sync"),
        "startup_kline_sync_target_candles": ("market", "startup_kline_sync_target_candles"),
        "ccxt_timeout_ms": ("market", "ccxt_timeout_ms"),
        "enable_ccxt_backfill": ("market", "enable_ccxt_backfill"),
        "enable_ccxt_backfill_on_read": ("market", "enable_ccxt_backfill_on_read"),
        "market_history_source": ("market", "market_history_source"),
        "enable_derived_timeframes": ("derived", "enable_derived_timeframes"),
        "derived_base_timeframe": ("derived", "derived_base_timeframe"),
        "derived_timeframes": ("derived", "derived_timeframes"),
        "derived_backfill_base_candles": ("derived", "derived_backfill_base_candles"),
        "enable_replay_v1": ("replay", "enable_replay_v1"),
        "enable_replay_ensure_coverage": ("replay", "enable_replay_ensure_coverage"),
        "blocking_workers": ("execution", "blocking_workers"),
        "backtest_require_trades": ("execution", "backtest_require_trades"),
        "freqtrade_mock_enabled": ("execution", "freqtrade_mock_enabled"),
    }

    def __getattr__(self, name: str) -> Any:
        pair = self._ALIASES.get(name)
        if pair is None:
            raise AttributeError(name)
        group_name, field_name = pair
        group = object.__getattribute__(self, group_name)
        return getattr(group, field_name)
