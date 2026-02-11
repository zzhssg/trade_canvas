from __future__ import annotations

from backend.app.flags import load_feature_flags, resolve_env_float, resolve_env_int, resolve_env_str


def test_feature_flags_defaults(monkeypatch) -> None:
    for name in (
        "TRADE_CANVAS_ENABLE_DEBUG_API",
        "TRADE_CANVAS_ENABLE_WHITELIST_INGEST",
        "TRADE_CANVAS_ENABLE_ONDEMAND_INGEST",
        "TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL",
        "TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES",
        "TRADE_CANVAS_ONDEMAND_IDLE_TTL_S",
    ):
        monkeypatch.delenv(name, raising=False)

    flags = load_feature_flags()
    assert flags.enable_debug_api is False
    assert flags.enable_whitelist_ingest is False
    assert flags.enable_ondemand_ingest is False
    assert flags.enable_market_auto_tail_backfill is False
    assert flags.market_auto_tail_backfill_max_candles is None
    assert flags.ondemand_idle_ttl_s == 60


def test_feature_flags_env_parsing(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_DEBUG_API", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_WHITELIST_INGEST", "yes")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST", "1")
    monkeypatch.setenv("TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL", "1")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES", "800")
    monkeypatch.setenv("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", "0")

    flags = load_feature_flags()
    assert flags.enable_debug_api is True
    assert flags.enable_whitelist_ingest is True
    assert flags.enable_ondemand_ingest is True
    assert flags.enable_market_auto_tail_backfill is True
    assert flags.market_auto_tail_backfill_max_candles == 800
    assert flags.ondemand_idle_ttl_s == 1


def test_resolve_env_int_prefers_runtime_env_and_fallback(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_ONDEMAND_MAX_JOBS", raising=False)
    assert resolve_env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", fallback=3, minimum=0) == 3

    monkeypatch.setenv("TRADE_CANVAS_ONDEMAND_MAX_JOBS", "7")
    assert resolve_env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", fallback=3, minimum=0) == 7

    monkeypatch.setenv("TRADE_CANVAS_ONDEMAND_MAX_JOBS", "bad")
    assert resolve_env_int("TRADE_CANVAS_ONDEMAND_MAX_JOBS", fallback=3, minimum=0) == 3


def test_resolve_env_str_prefers_runtime_env_and_strips(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_BINANCE_SPOT_BASE_URL", raising=False)
    assert resolve_env_str("TRADE_CANVAS_BINANCE_SPOT_BASE_URL", fallback="https://api.binance.com") == "https://api.binance.com"

    monkeypatch.setenv("TRADE_CANVAS_BINANCE_SPOT_BASE_URL", "  https://example.com  ")
    assert resolve_env_str("TRADE_CANVAS_BINANCE_SPOT_BASE_URL", fallback="unused") == "https://example.com"


def test_resolve_env_float_prefers_runtime_env_and_clamps(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_BINANCE_WS_FLUSH_S", raising=False)
    assert resolve_env_float("TRADE_CANVAS_BINANCE_WS_FLUSH_S", fallback=0.5, minimum=0.05) == 0.5

    monkeypatch.setenv("TRADE_CANVAS_BINANCE_WS_FLUSH_S", "0.2")
    assert resolve_env_float("TRADE_CANVAS_BINANCE_WS_FLUSH_S", fallback=0.5, minimum=0.05) == 0.2

    monkeypatch.setenv("TRADE_CANVAS_BINANCE_WS_FLUSH_S", "bad")
    assert resolve_env_float("TRADE_CANVAS_BINANCE_WS_FLUSH_S", fallback=0.5, minimum=0.05) == 0.5

    monkeypatch.setenv("TRADE_CANVAS_BINANCE_WS_FLUSH_S", "0")
    assert resolve_env_float("TRADE_CANVAS_BINANCE_WS_FLUSH_S", fallback=0.5, minimum=0.05) == 0.05
