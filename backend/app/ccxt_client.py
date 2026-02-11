from __future__ import annotations

from .series_id import SeriesId


def _make_exchange_client(series: SeriesId, *, timeout_ms: int = 10_000):
    import ccxt  # imported lazily so tests don't require it unless a path needs ccxt

    if series.exchange != "binance":
        raise ValueError(f"unsupported exchange: {series.exchange!r}")

    timeout = max(1000, int(timeout_ms))
    options = {"enableRateLimit": True, "timeout": timeout}
    if series.market == "spot":
        return ccxt.binance(options)
    if series.market == "futures":
        return ccxt.binanceusdm(options)
    raise ValueError(f"unsupported market: {series.market!r}")


def ccxt_symbol_for_series(series: SeriesId) -> str:
    if series.market != "futures":
        return series.symbol

    if ":" in series.symbol:
        return series.symbol

    if "/" not in series.symbol:
        return series.symbol

    base, quote = series.symbol.split("/", 1)
    base = base.strip()
    quote = quote.strip()
    if not base or not quote:
        return series.symbol
    return f"{base}/{quote}:{quote}"
