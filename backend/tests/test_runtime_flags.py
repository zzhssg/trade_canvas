from __future__ import annotations

from backend.app.flags import FeatureFlags
from backend.app.runtime_flags import load_runtime_flags


def _base_flags(*, enable_market_auto_tail_backfill: bool) -> FeatureFlags:
    return FeatureFlags(
        enable_debug_api=False,
        enable_read_strict_mode=False,
        enable_whitelist_ingest=False,
        enable_ondemand_ingest=False,
        enable_market_auto_tail_backfill=bool(enable_market_auto_tail_backfill),
        market_auto_tail_backfill_max_candles=None,
        ondemand_idle_ttl_s=60,
    )


def test_runtime_flags_ccxt_backfill_on_read_defaults_to_auto_tail_backfill(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", raising=False)
    auto_tail_on = load_runtime_flags(base_flags=_base_flags(enable_market_auto_tail_backfill=True))
    auto_tail_off = load_runtime_flags(base_flags=_base_flags(enable_market_auto_tail_backfill=False))

    assert auto_tail_on.enable_ccxt_backfill_on_read is True
    assert auto_tail_off.enable_ccxt_backfill_on_read is False


def test_runtime_flags_ccxt_backfill_on_read_env_override_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", "0")
    override_off = load_runtime_flags(base_flags=_base_flags(enable_market_auto_tail_backfill=True))
    assert override_off.enable_ccxt_backfill_on_read is False

    monkeypatch.setenv("TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ", "1")
    override_on = load_runtime_flags(base_flags=_base_flags(enable_market_auto_tail_backfill=False))
    assert override_on.enable_ccxt_backfill_on_read is True


def test_runtime_flags_replay_and_overlay_controls(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_FACTOR_INGEST", "0")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD", "0")
    monkeypatch.setenv("TRADE_CANVAS_PIVOT_WINDOW_MAJOR", "0")
    monkeypatch.setenv("TRADE_CANVAS_PIVOT_WINDOW_MINOR", "-1")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES", "9")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT", "99")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "10")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_LOGIC_VERSION", "fingerprint-v2")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_OVERLAY_INGEST", "0")
    monkeypatch.setenv("TRADE_CANVAS_OVERLAY_WINDOW_CANDLES", "9")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_OVERLAY_ERROR", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_NEW_CANDLES", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_READ_REPAIR_API", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_STARTUP_KLINE_SYNC", "1")
    monkeypatch.setenv("TRADE_CANVAS_STARTUP_KLINE_SYNC_TARGET_CANDLES", "9")
    monkeypatch.setenv("TRADE_CANVAS_CCXT_TIMEOUT_MS", "9")
    monkeypatch.setenv("TRADE_CANVAS_BLOCKING_WORKERS", "0")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_REPLAY_V1", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_REPLAY_PACKAGE", "1")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_HISTORY_SOURCE", "freqtrade")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES", "1")
    monkeypatch.setenv("TRADE_CANVAS_DERIVED_BASE_TIMEFRAME", "3m")
    monkeypatch.setenv("TRADE_CANVAS_DERIVED_TIMEFRAMES", "6m,12m,6m")
    monkeypatch.setenv("TRADE_CANVAS_DERIVED_BACKFILL_BASE_CANDLES", "9")
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_WS_BATCH_MAX", "0")
    monkeypatch.setenv("TRADE_CANVAS_BINANCE_WS_FLUSH_S", "0.01")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS", "-10")

    flags = load_runtime_flags(base_flags=_base_flags(enable_market_auto_tail_backfill=False))

    assert flags.enable_factor_ingest is False
    assert flags.enable_factor_fingerprint_rebuild is False
    assert flags.factor_pivot_window_major == 1
    assert flags.factor_pivot_window_minor == 1
    assert flags.factor_lookback_candles == 100
    assert flags.factor_state_rebuild_event_limit == 1000
    assert flags.factor_rebuild_keep_candles == 100
    assert flags.factor_logic_version_override == "fingerprint-v2"
    assert flags.enable_overlay_ingest is False
    assert flags.overlay_window_candles == 100
    assert flags.enable_ingest_compensate_overlay_error is True
    assert flags.enable_ingest_compensate_new_candles is True
    assert flags.enable_read_repair_api is True
    assert flags.enable_startup_kline_sync is True
    assert flags.startup_kline_sync_target_candles == 100
    assert flags.ccxt_timeout_ms == 1000
    assert flags.blocking_workers == 1
    assert flags.enable_replay_v1 is True
    assert flags.enable_replay_ensure_coverage is True
    assert flags.enable_replay_package is True
    assert flags.market_history_source == "freqtrade"
    assert flags.enable_derived_timeframes is True
    assert flags.derived_base_timeframe == "3m"
    assert flags.derived_timeframes == ("6m", "12m")
    assert flags.derived_backfill_base_candles == 100
    assert flags.binance_ws_batch_max == 1
    assert abs(flags.binance_ws_flush_s - 0.05) < 1e-9
    assert flags.market_forming_min_interval_ms == 0
