from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.factor_plugin_contract import FactorPluginSpec
from backend.app.freqtrade_adapter_v1 import annotate_factor_ledger
from backend.app.freqtrade_signal_plugin_contract import (
    FreqtradeSignalBucketSpec,
    FreqtradeSignalContext,
)


class FreqtradeAdapterV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
        ):
            os.environ.pop(k, None)

    def _build_df(self, prices: list[float]) -> pd.DataFrame:
        base = 60
        times = [base * (i + 1) for i in range(len(prices))]
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(times, unit="s", utc=True),
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
                "volume": [1.0] * len(prices),
            }
        )
        return df

    def test_adapter_generates_pen_events(self) -> None:
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1, 2, 5, 2, 1]
        df = self._build_df(prices)

        res = annotate_factor_ledger(df, series_id=self.series_id, timeframe="1m", db_path=self.db_path)
        self.assertTrue(res.ok, res.reason)
        out = res.dataframe

        self.assertIn("tc_ok", out)
        self.assertEqual(int(out["tc_ok"].iloc[-1]), 1)
        self.assertIn("tc_pen_confirmed", out)
        self.assertGreaterEqual(int(out["tc_pen_confirmed"].sum()), 1)

        enters = out.index[out["tc_enter_long"] == 1].tolist()
        for idx in enters:
            self.assertEqual(int(out.at[idx, "tc_pen_confirmed"]), 1)
            self.assertEqual(int(out.at[idx, "tc_pen_dir"]), 1)

    def test_adapter_fails_when_ledger_out_of_sync(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "0"
        prices = [1, 2, 5, 2, 1]
        df = self._build_df(prices)

        res = annotate_factor_ledger(df, series_id=self.series_id, timeframe="1m", db_path=self.db_path)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "ledger_out_of_sync")
        out = res.dataframe
        self.assertTrue((out["tc_ok"] == 0).all())
        self.assertTrue((out["tc_enter_long"] == 0).all())

    def test_adapter_supports_custom_signal_plugin(self) -> None:
        class _PivotSignalPlugin:
            spec = FactorPluginSpec(factor_name="signal.pivot", depends_on=())
            bucket_specs = (
                FreqtradeSignalBucketSpec(
                    factor_name="pivot",
                    event_kind="pivot.major",
                    bucket_name="pivot_major",
                    sort_keys=("visible_time", "pivot_time"),
                ),
            )

            def prepare_dataframe(self, *, dataframe: pd.DataFrame) -> None:
                dataframe["tc_pivot_major_seen"] = 0

            def apply(self, *, ctx: FreqtradeSignalContext) -> None:
                seen_times = {
                    int(payload.get("visible_time") or payload.get("candle_time") or 0)
                    for payload in list(ctx.buckets.get("pivot_major") or [])
                    if int(payload.get("visible_time") or payload.get("candle_time") or 0) > 0
                }
                for idx in ctx.order:
                    t = int(ctx.times_by_index.get(idx) or 0)
                    if t in seen_times:
                        ctx.dataframe.at[idx, "tc_pivot_major_seen"] = 1

        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1, 2, 5, 2, 1]
        df = self._build_df(prices)

        res = annotate_factor_ledger(
            df,
            series_id=self.series_id,
            timeframe="1m",
            db_path=self.db_path,
            signal_plugins=(_PivotSignalPlugin(),),
        )
        self.assertTrue(res.ok, res.reason)
        out = res.dataframe
        self.assertIn("tc_pivot_major_seen", out.columns)
        self.assertGreaterEqual(int(out["tc_pivot_major_seen"].sum()), 1)


if __name__ == "__main__":
    unittest.main()
