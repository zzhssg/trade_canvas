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
