from __future__ import annotations

from backend.app.factor_runtime_config import (
    FactorSettings,
    factor_ingest_enabled,
    factor_rebuild_keep_candles,
    load_factor_settings,
)


def test_factor_ingest_enabled_defaults_to_true(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_ENABLE_FACTOR_INGEST", raising=False)
    assert factor_ingest_enabled() is True


def test_factor_rebuild_keep_candles_clamps_and_fallback(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", raising=False)
    assert factor_rebuild_keep_candles() == 2000

    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "50")
    assert factor_rebuild_keep_candles() == 100

    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "bad")
    assert factor_rebuild_keep_candles() == 2000


def test_load_factor_settings_reads_and_clamps_env(monkeypatch) -> None:
    defaults = FactorSettings(
        pivot_window_major=20,
        pivot_window_minor=2,
        lookback_candles=5000,
        state_rebuild_event_limit=8000,
    )
    monkeypatch.setenv("TRADE_CANVAS_PIVOT_WINDOW_MAJOR", "1")
    monkeypatch.setenv("TRADE_CANVAS_PIVOT_WINDOW_MINOR", "0")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES", "80")
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT", "900")

    out = load_factor_settings(defaults=defaults)
    assert out.pivot_window_major == 1
    assert out.pivot_window_minor == 1
    assert out.lookback_candles == 100
    assert out.state_rebuild_event_limit == 1000
