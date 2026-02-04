from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class OfflineSpotMarketSpec:
    symbol: str
    base: str
    quote: str
    market_id: str


def _parse_spot_pair(pair: str) -> OfflineSpotMarketSpec:
    s = pair.strip()
    if ":" in s:
        s = s.split(":", 1)[0].strip()
    if "/" not in s:
        raise ValueError(f"invalid spot pair: {pair!r}")
    base, quote = s.split("/", 1)
    base = base.strip()
    quote = quote.strip()
    if not base or not quote:
        raise ValueError(f"invalid spot pair: {pair!r}")
    return OfflineSpotMarketSpec(symbol=f"{base}/{quote}", base=base, quote=quote, market_id=f"{base}{quote}")


def build_ccxt_spot_markets(*, pairs: Iterable[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Build a minimal ccxt markets + currencies dict for offline spot backtesting.

    Notes:
    - In this repo's ccxt (4.5.x), binance uses precisionMode=TICK_SIZE, so `precision` values are tick sizes.
    - This is for backtesting/debug only, not meant to match full exchange metadata.
    """
    markets: dict[str, dict[str, Any]] = {}
    currencies: dict[str, dict[str, Any]] = {}

    for raw in pairs:
        spec = _parse_spot_pair(str(raw))
        markets[spec.symbol] = {
            "id": spec.market_id,
            "symbol": spec.symbol,
            "base": spec.base,
            "quote": spec.quote,
            "settle": None,
            "active": True,
            "type": "spot",
            "spot": True,
            "margin": False,
            "swap": False,
            "future": False,
            "option": False,
            "contract": False,
            "linear": False,
            "inverse": False,
            "precision": {"price": 0.01, "amount": 0.000001},
            "limits": {
                "amount": {"min": 0.0001, "max": 1_000_000},
                "price": {"min": 0.01, "max": 1_000_000_000},
                "cost": {"min": 0, "max": 1_000_000_000_000},
            },
        }

        for code in (spec.base, spec.quote):
            currencies.setdefault(
                code,
                {
                    "id": code,
                    "code": code,
                    "name": code,
                    "active": True,
                    "precision": 1e-8,
                    "limits": {"amount": {"min": 0, "max": None}, "withdraw": {"min": 0, "max": None}},
                },
            )

    return markets, currencies

