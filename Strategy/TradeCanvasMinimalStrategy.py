from __future__ import annotations

from typing import Any

import pandas as pd

from freqtrade.strategy import IStrategy


class TradeCanvasMinimalStrategy(IStrategy):
    """
    Minimal, dependency-light strategy intended for smoke-testing freqtrade backtesting.

    Logic:
    - Indicators: SMA(fast=5), SMA(slow=20)
    - Entry: fast crosses above slow
    - Exit: fast crosses below slow
    """

    timeframe = "1m"
    can_short = False

    minimal_roi = {"0": 0.01}
    stoploss = -0.10

    process_only_new_candles = True
    startup_candle_count = 30

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        df["sma_fast"] = df["close"].rolling(5, min_periods=5).mean()
        df["sma_slow"] = df["close"].rolling(20, min_periods=20).mean()
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        cross_up = (df["sma_fast"] > df["sma_slow"]) & (df["sma_fast"].shift(1) <= df["sma_slow"].shift(1))
        df.loc[cross_up & (df["volume"] > 0), "enter_long"] = 1
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        cross_down = (df["sma_fast"] < df["sma_slow"]) & (df["sma_fast"].shift(1) >= df["sma_slow"].shift(1))
        df.loc[cross_down, "exit_long"] = 1
        return df

