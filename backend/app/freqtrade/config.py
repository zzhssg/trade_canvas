from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


_OPTIONAL_SECTIONS = [
    "unfilledtimeout",
    "entry_pricing",
    "exit_pricing",
    "order_types",
    "order_time_in_force",
    "protections",
    "position_adjustment",
    "edge",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_backtest_config(
    base: dict[str, Any],
    *,
    pair: str,
    timeframe: str,
) -> dict[str, Any]:
    """
    Build a minimal freqtrade config for backtesting.

    Goal: stable + small (do not inherit trade_system's complexity).
    - Keep exchange wiring and datadir from base config.
    - Force pairlist to StaticPairList + single pair to avoid huge runs.
    - Ensure required keys exist (e.g., stoploss) to avoid runtime KeyError.
    """
    exchange_base = dict(base.get("exchange") or {})
    exchange: dict[str, Any] = {
        "name": exchange_base.get("name") or "binance",
        "ccxt_config": exchange_base.get("ccxt_config") or {},
        "ccxt_async_config": exchange_base.get("ccxt_async_config") or {},
        "pair_whitelist": [pair],
        "pair_blacklist": list(exchange_base.get("pair_blacklist") or []),
    }

    cfg: dict[str, Any] = {
        "$schema": base.get("$schema") or "https://schema.freqtrade.io/schema.json",
        "dry_run": True,
        "dry_run_wallet": base.get("dry_run_wallet", 1000),
        "max_open_trades": base.get("max_open_trades", 3),
        "stake_currency": base.get("stake_currency", "USDT"),
        "stake_amount": base.get("stake_amount", "unlimited"),
        "tradable_balance_ratio": base.get("tradable_balance_ratio", 0.99),
        "fiat_display_currency": base.get("fiat_display_currency", "USD"),
        "trading_mode": base.get("trading_mode", "spot"),
        "margin_mode": base.get("margin_mode", ""),
        "timeframe": timeframe,
        "datadir": base.get("datadir", "user_data/data"),
        "minimal_roi": base.get("minimal_roi", {}),
        "stoploss": base.get("stoploss", -1.0),
        "trailing_stop": base.get("trailing_stop", False),
        "trailing_stop_positive": base.get("trailing_stop_positive", 0.0),
        "trailing_stop_positive_offset": base.get("trailing_stop_positive_offset", 0.0),
        "trailing_only_offset_is_reached": base.get("trailing_only_offset_is_reached", False),
        "use_exit_signal": base.get("use_exit_signal", True),
        "exit_profit_only": base.get("exit_profit_only", False),
        "exit_profit_offset": base.get("exit_profit_offset", 0.0),
        "ignore_roi_if_entry_signal": base.get("ignore_roi_if_entry_signal", False),
        "ignore_buying_expired_candle_after": base.get("ignore_buying_expired_candle_after", 0),
        "exchange": exchange,
        "pairlists": [{"method": "StaticPairList"}],
        "internals": base.get("internals", {"process_throttle_secs": 5}),
    }

    for key in _OPTIONAL_SECTIONS:
        if key in base:
            cfg[key] = base[key]

    # Ensure these exist even if base config is "live-only".
    cfg.setdefault("cancel_open_orders_on_exit", False)
    cfg.setdefault("unfilledtimeout", {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"})
    cfg.setdefault("entry_pricing", {"price_side": "same", "use_order_book": True, "order_book_top": 1})
    cfg.setdefault("exit_pricing", {"price_side": "same", "use_order_book": True, "order_book_top": 1})
    cfg.setdefault(
        "order_types",
        {"entry": "limit", "exit": "limit", "stoploss": "limit", "stoploss_on_exchange": False},
    )

    return cfg


def write_temp_config(config: dict[str, Any], *, root_dir: Path) -> Path:
    root_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        prefix="trade_canvas_bt_",
        suffix=".json",
        dir=str(root_dir),
    ) as f:
        json.dump(config, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        return Path(f.name)
