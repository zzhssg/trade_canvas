from __future__ import annotations

from backend.app.core.flags import resolve_env_float, resolve_env_int, resolve_env_str


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
