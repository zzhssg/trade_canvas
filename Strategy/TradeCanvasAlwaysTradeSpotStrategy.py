from __future__ import annotations

from typing import Any

import pandas as pd

from freqtrade.strategy import IStrategy


class TradeCanvasAlwaysTradeSpotStrategy(IStrategy):
    """
    Debug-only strategy for backtesting E2E: force producing trades on spot markets.

    Logic:
    - Entry: always enter long (after startup) when volume > 0.
    - Exit: exit long every N candles.
    """

    timeframe = "1m"
    can_short = False

    minimal_roi = {"0": 0.0}
    stoploss = -0.99

    process_only_new_candles = True
    startup_candle_count = 5

    exit_after_candles = 10

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        df["tc_idx"] = range(len(df))
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        df.loc[(df["volume"] > 0) & (df["tc_idx"] >= self.startup_candle_count), "enter_long"] = 1
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        n = max(1, int(self.exit_after_candles))
        eligible = df["tc_idx"] >= (self.startup_candle_count + n)
        df.loc[(df["volume"] > 0) & eligible & ((df["tc_idx"] - self.startup_candle_count) % n == 0), "exit_long"] = 1
        return df

