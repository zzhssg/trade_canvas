from __future__ import annotations

from backend.app.core.config import load_settings


def test_market_settings_defaults(monkeypatch) -> None:
    for name in (
        "TRADE_CANVAS_MARKET_WS_CATCHUP_LIMIT",
        "TRADE_CANVAS_MARKET_GAP_BACKFILL_READ_LIMIT",
        "TRADE_CANVAS_MARKET_FRESH_WINDOW_CANDLES",
        "TRADE_CANVAS_MARKET_STALE_WINDOW_CANDLES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()
    assert settings.market_ws_catchup_limit == 5000
    assert settings.market_gap_backfill_read_limit == 5000
    assert settings.market_fresh_window_candles == 2
    assert settings.market_stale_window_candles == 5
    assert settings.postgres_dsn == ""
    assert settings.postgres_schema == "public"
    assert settings.postgres_connect_timeout_s == 5.0
    assert settings.postgres_pool_min_size == 1
    assert settings.postgres_pool_max_size == 10
    assert settings.redis_url == ""
    assert settings.freqtrade_datadir is None


def test_market_settings_env_is_clamped(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_MARKET_WS_CATCHUP_LIMIT", "10")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_GAP_BACKFILL_READ_LIMIT", "bad")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_FRESH_WINDOW_CANDLES", "8")
    monkeypatch.setenv("TRADE_CANVAS_MARKET_STALE_WINDOW_CANDLES", "5")

    settings = load_settings()
    assert settings.market_ws_catchup_limit == 100
    assert settings.market_gap_backfill_read_limit == 5000
    assert settings.market_fresh_window_candles == 8
    assert settings.market_stale_window_candles == 9


def test_freqtrade_datadir_from_env(monkeypatch, tmp_path) -> None:
    datadir = tmp_path / "data"
    datadir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TRADE_CANVAS_FREQTRADE_DATADIR", str(datadir))
    settings = load_settings()
    assert settings.freqtrade_datadir == datadir.resolve()


def test_postgres_and_redis_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_POSTGRES_DSN", "postgresql://tc:tc@127.0.0.1:5432/tc")
    monkeypatch.setenv("TRADE_CANVAS_POSTGRES_SCHEMA", "trade_canvas")
    monkeypatch.setenv("TRADE_CANVAS_POSTGRES_CONNECT_TIMEOUT_S", "0")
    monkeypatch.setenv("TRADE_CANVAS_POSTGRES_POOL_MIN_SIZE", "0")
    monkeypatch.setenv("TRADE_CANVAS_POSTGRES_POOL_MAX_SIZE", "2")
    monkeypatch.setenv("TRADE_CANVAS_REDIS_URL", "redis://127.0.0.1:6379/0")

    settings = load_settings()
    assert settings.postgres_dsn == "postgresql://tc:tc@127.0.0.1:5432/tc"
    assert settings.postgres_schema == "trade_canvas"
    assert settings.postgres_connect_timeout_s == 0.1
    assert settings.postgres_pool_min_size == 1
    assert settings.postgres_pool_max_size == 2
    assert settings.redis_url == "redis://127.0.0.1:6379/0"
