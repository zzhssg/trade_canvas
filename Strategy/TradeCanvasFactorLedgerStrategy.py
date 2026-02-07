from __future__ import annotations

from typing import Any

import pandas as pd

from freqtrade.strategy import IStrategy

from backend.app.freqtrade_adapter_v1 import annotate_factor_ledger, build_series_id


class TradeCanvasFactorLedgerStrategy(IStrategy):
    """
    Factor-ledger driven strategy (demo):
    - Uses trade_canvas factor ledger as the single source of truth.
    - Entry/exit signals are derived from pen.confirmed events.
    """

    timeframe = "1m"
    can_short = True

    minimal_roi = {"0": 0.01}
    stoploss = -0.10

    process_only_new_candles = True
    startup_candle_count = 100

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        series_id = build_series_id(metadata.get("pair", ""), self.timeframe)
        res = annotate_factor_ledger(dataframe, series_id=series_id, timeframe=self.timeframe)
        return res.dataframe if res.ok else dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        df.loc[(df.get("tc_ok") == 1) & (df.get("tc_enter_long") == 1) & (df["volume"] > 0), "enter_long"] = 1
        df.loc[(df.get("tc_ok") == 1) & (df.get("tc_enter_short") == 1) & (df["volume"] > 0), "enter_short"] = 1
        return df

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        df = dataframe.copy()
        df.loc[(df.get("tc_ok") == 1) & (df.get("tc_enter_short") == 1), "exit_long"] = 1
        df.loc[(df.get("tc_ok") == 1) & (df.get("tc_enter_long") == 1), "exit_short"] = 1
        return df
