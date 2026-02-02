from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeriesId:
    exchange: str
    market: str
    symbol: str
    timeframe: str

    @property
    def raw(self) -> str:
        return f"{self.exchange}:{self.market}:{self.symbol}:{self.timeframe}"


def parse_series_id(series_id: str) -> SeriesId:
    # Support symbols that may contain ':' (e.g. CCXT futures symbols like "BTC/USDT:USDT").
    parts = series_id.split(":")
    if len(parts) < 4:
        raise ValueError("series_id must be '{exchange}:{market}:{symbol}:{timeframe}'")
    exchange = parts[0].strip()
    market = parts[1].strip()
    timeframe = parts[-1].strip()
    symbol = ":".join(parts[2:-1]).strip()
    if not exchange or not market or not symbol or not timeframe:
        raise ValueError("invalid series_id (empty component)")
    return SeriesId(exchange=exchange, market=market, symbol=symbol, timeframe=timeframe)
