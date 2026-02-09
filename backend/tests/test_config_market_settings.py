from __future__ import annotations

from backend.app.config import load_settings


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
