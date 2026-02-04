from __future__ import annotations

import os
from typing import Any


def _enabled() -> bool:
    return (os.environ.get("TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS") or "").strip() == "1"


def _parse_pairs_env() -> list[str]:
    raw = (os.environ.get("TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS_PAIRS") or "").strip()
    if not raw:
        return ["BTC/USDT"]

    parts: list[str] = []
    for chunk in raw.replace("\n", " ").replace("\t", " ").split(" "):
        chunk = chunk.strip()
        if not chunk:
            continue
        for s in chunk.split(","):
            s = s.strip()
            if s:
                parts.append(s)

    uniq: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq or ["BTC/USDT"]


def _install_ccxt_patch() -> None:
    import ccxt  # type: ignore
    import ccxt.async_support  # type: ignore

    from trade_canvas.offline_markets import build_ccxt_spot_markets

    pairs = _parse_pairs_env()
    markets, currencies = build_ccxt_spot_markets(pairs=pairs)

    def _tc_load_markets(self: Any, reload: bool = False, params: dict | None = None) -> Any:
        self.set_markets(markets, currencies=currencies)
        return self.markets

    async def _tc_load_markets_async(self: Any, reload: bool = False, params: dict | None = None) -> Any:
        self.set_markets(markets, currencies=currencies)
        return self.markets

    ccxt.binance.load_markets = _tc_load_markets  # type: ignore[attr-defined]
    ccxt.async_support.binance.load_markets = _tc_load_markets_async  # type: ignore[attr-defined]


if _enabled():
    try:
        _install_ccxt_patch()
    except Exception:
        # Fail-safe: do not break other tooling if patching fails.
        pass

