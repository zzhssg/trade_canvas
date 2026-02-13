from __future__ import annotations

from ..core.series_id import SeriesId


def _make_exchange_client(series: SeriesId, *, timeout_ms: int = 10_000):
    import ccxt  # type: ignore[import-untyped]  # imported lazily so tests don't require it unless a path needs ccxt

    if series.exchange != "binance":
        raise ValueError(f"unsupported exchange: {series.exchange!r}")

    timeout = max(1000, int(timeout_ms))
    options = {"enableRateLimit": True, "timeout": timeout}
    if series.market == "spot":
        exchange = ccxt.binance(options)
    elif series.market == "futures":
        exchange = ccxt.binanceusdm(options)
    else:
        raise ValueError(f"unsupported market: {series.market!r}")

    # Keep proxy behavior consistent with plain requests: respect env proxy variables
    # when present (for example https_proxy in local dev).
    session = getattr(exchange, "session", None)
    if session is not None:
        try:
            session.trust_env = True
        except Exception:
            pass
    return exchange


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
