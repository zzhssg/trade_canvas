from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandleClosed:
    symbol: str
    timeframe: str
    open_time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def candle_id(self) -> str:
        return f"{self.symbol}:{self.timeframe}:{self.open_time}"

