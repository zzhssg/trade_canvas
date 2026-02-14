from __future__ import annotations

import os

from ..market.derived_timeframes import DEFAULT_DERIVED_TIMEFRAMES, normalize_derived_timeframes
from ..core.flags import env_bool, env_int, resolve_env_float, resolve_env_str
from .flags_models import (
    RuntimeApiFlags,
    RuntimeDerivedFlags,
    RuntimeExecutionFlags,
    RuntimeFactorFlags,
    RuntimeFlags,
    RuntimeIngestFlags,
    RuntimeMarketFlags,
    RuntimeOverlayFlags,
    RuntimeReplayFlags,
    RuntimeScaleoutFlags,
)


def _env_csv(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return tuple(default)
    return normalize_derived_timeframes(part.strip() for part in raw.split(","))


def _normalize_ingest_role(raw: str) -> str:
    role = str(raw or "").strip().lower()
    if role in {"hybrid", "ingest", "read"}:
        return role
    return "hybrid"


def load_runtime_flags() -> RuntimeFlags:
    enable_market_auto_tail_backfill = env_bool("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL")
    max_candles_raw = (os.environ.get("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES") or "").strip()
    max_candles: int | None = None
    if max_candles_raw:
        try:
            parsed = int(max_candles_raw)
            if parsed > 0:
                max_candles = parsed
        except ValueError:
            max_candles = None

    api = RuntimeApiFlags(
        enable_debug_api=env_bool("TRADE_CANVAS_ENABLE_DEBUG_API"),
        enable_dev_api=env_bool("TRADE_CANVAS_ENABLE_DEV_API", default=False),
        enable_runtime_metrics=env_bool("TRADE_CANVAS_ENABLE_RUNTIME_METRICS", default=False),
        enable_capacity_metrics=env_bool("TRADE_CANVAS_ENABLE_CAPACITY_METRICS", default=False),
        enable_read_ledger_warmup=env_bool(
            "TRADE_CANVAS_ENABLE_READ_LEDGER_WARMUP",
            default=enable_market_auto_tail_backfill,
        ),
        enable_kline_health_v2=env_bool("TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2"),
        enable_read_repair_api=env_bool("TRADE_CANVAS_ENABLE_READ_REPAIR_API"),
        kline_health_backfill_recent_seconds=env_int(
            "TRADE_CANVAS_KLINE_HEALTH_BACKFILL_RECENT_SECONDS",
            default=120,
            minimum=5,
        ),
    )

    scaleout = RuntimeScaleoutFlags(
        enable_pg_store=env_bool("TRADE_CANVAS_ENABLE_PG_STORE", default=False),
        enable_pg_only=env_bool("TRADE_CANVAS_ENABLE_PG_ONLY", default=False),
        enable_ws_pubsub=env_bool("TRADE_CANVAS_ENABLE_WS_PUBSUB", default=False),
    )

    factor = RuntimeFactorFlags(
        enable_factor_ingest=env_bool("TRADE_CANVAS_ENABLE_FACTOR_INGEST", default=True),
        enable_factor_fingerprint_rebuild=env_bool("TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD", default=True),
        pivot_window_major=env_int(
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            default=50,
            minimum=1,
        ),
        pivot_window_minor=env_int(
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            default=5,
            minimum=1,
        ),
        lookback_candles=env_int(
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            default=20000,
            minimum=100,
        ),
        state_rebuild_event_limit=env_int(
            "TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT",
            default=50000,
            minimum=1000,
        ),
        rebuild_keep_candles=env_int(
            "TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES",
            default=2000,
            minimum=100,
        ),
        logic_version_override=resolve_env_str("TRADE_CANVAS_FACTOR_LOGIC_VERSION"),
    )

    overlay = RuntimeOverlayFlags(
        enable_overlay_ingest=env_bool("TRADE_CANVAS_ENABLE_OVERLAY_INGEST", default=True),
        window_candles=env_int(
            "TRADE_CANVAS_OVERLAY_WINDOW_CANDLES",
            default=2000,
            minimum=100,
        ),
    )

    ingest = RuntimeIngestFlags(
        enable_ingest_role_guard=env_bool("TRADE_CANVAS_ENABLE_INGEST_ROLE_GUARD", default=False),
        ingest_role=_normalize_ingest_role(resolve_env_str("TRADE_CANVAS_INGEST_ROLE", fallback="hybrid")),
        enable_ingest_compensate_overlay_error=env_bool("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_OVERLAY_ERROR"),
        enable_ingest_compensate_new_candles=env_bool("TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_NEW_CANDLES"),
        enable_ingest_loop_guardrail=env_bool("TRADE_CANVAS_ENABLE_INGEST_LOOP_GUARDRAIL", default=False),
        enable_whitelist_ingest=env_bool("TRADE_CANVAS_ENABLE_WHITELIST_INGEST"),
        enable_ondemand_ingest=env_bool("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"),
        ondemand_idle_ttl_s=env_int("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", default=60, minimum=1),
        ondemand_max_jobs=env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", default=0, minimum=0),
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

    market = RuntimeMarketFlags(
        enable_market_auto_tail_backfill=enable_market_auto_tail_backfill,
        enable_strict_closed_only=env_bool("TRADE_CANVAS_ENABLE_STRICT_CLOSED_ONLY", default=False),
        market_auto_tail_backfill_max_candles=max_candles,
        enable_market_backfill_progress_persistence=env_bool(
            "TRADE_CANVAS_ENABLE_MARKET_BACKFILL_PROGRESS_PERSISTENCE",
            default=False,
        ),
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
        enable_ccxt_backfill=env_bool("TRADE_CANVAS_ENABLE_CCXT_BACKFILL"),
        enable_ccxt_backfill_on_read=env_bool(
            "TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ",
            default=enable_market_auto_tail_backfill,
        ),
        market_history_source=resolve_env_str("TRADE_CANVAS_MARKET_HISTORY_SOURCE", fallback="").lower(),
    )

    derived = RuntimeDerivedFlags(
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
    )

    replay = RuntimeReplayFlags(
        enable_replay_v1=env_bool("TRADE_CANVAS_ENABLE_REPLAY_V1"),
        enable_replay_ensure_coverage=env_bool("TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE"),
        enable_replay_package=env_bool("TRADE_CANVAS_ENABLE_REPLAY_PACKAGE"),
    )

    execution = RuntimeExecutionFlags(
        blocking_workers=env_int(
            "TRADE_CANVAS_BLOCKING_WORKERS",
            default=8,
            minimum=1,
        ),
        backtest_require_trades=env_bool("TRADE_CANVAS_BACKTEST_REQUIRE_TRADES"),
        freqtrade_mock_enabled=env_bool("TRADE_CANVAS_FREQTRADE_MOCK"),
    )

    return RuntimeFlags(
        api=api,
        scaleout=scaleout,
        factor=factor,
        overlay=overlay,
        ingest=ingest,
        market=market,
        derived=derived,
        replay=replay,
        execution=execution,
    )


__all__ = [
    "RuntimeApiFlags",
    "RuntimeDerivedFlags",
    "RuntimeExecutionFlags",
    "RuntimeFactorFlags",
    "RuntimeFlags",
    "RuntimeIngestFlags",
    "RuntimeMarketFlags",
    "RuntimeOverlayFlags",
    "RuntimeReplayFlags",
    "RuntimeScaleoutFlags",
    "load_runtime_flags",
]
