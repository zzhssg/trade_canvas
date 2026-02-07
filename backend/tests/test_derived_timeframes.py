from __future__ import annotations

import unittest

from backend.app.derived_timeframes import DerivedTimeframeFanout, rollup_closed_candles, to_derived_series_id
from backend.app.schemas import CandleClosed


class DerivedTimeframesTests(unittest.TestCase):
    def test_rollup_closed_candles_5m_happy_path(self) -> None:
        base = [
            CandleClosed(candle_time=0, open=10, high=11, low=9, close=10.5, volume=1),
            CandleClosed(candle_time=60, open=10.5, high=12, low=10, close=11.0, volume=2),
            CandleClosed(candle_time=120, open=11.0, high=13, low=10.8, close=12.0, volume=3),
            CandleClosed(candle_time=180, open=12.0, high=12.2, low=11.5, close=11.9, volume=4),
            CandleClosed(candle_time=240, open=11.9, high=12.5, low=11.7, close=12.4, volume=5),
        ]
        derived = rollup_closed_candles(base_timeframe="1m", derived_timeframe="5m", base_candles=base)
        self.assertEqual(len(derived), 1)
        c = derived[0]
        self.assertEqual(int(c.candle_time), 0)
        self.assertAlmostEqual(float(c.open), 10.0)
        self.assertAlmostEqual(float(c.close), 12.4)
        self.assertAlmostEqual(float(c.high), 13.0)
        self.assertAlmostEqual(float(c.low), 9.0)
        self.assertAlmostEqual(float(c.volume), 15.0)

    def test_fanout_emits_derived_closed_when_bucket_complete(self) -> None:
        base_series_id = "binance:futures:BTC/USDT:1m"
        fanout = DerivedTimeframeFanout(base_timeframe="1m", derived=("5m",), forming_min_interval_ms=0)

        base = [
            CandleClosed(candle_time=0, open=1, high=2, low=0.5, close=1.5, volume=1),
            CandleClosed(candle_time=60, open=1.5, high=3, low=1.4, close=2.0, volume=1),
            CandleClosed(candle_time=120, open=2.0, high=2.2, low=1.8, close=2.1, volume=1),
            CandleClosed(candle_time=180, open=2.1, high=2.3, low=1.9, close=2.2, volume=1),
            CandleClosed(candle_time=240, open=2.2, high=2.4, low=2.0, close=2.3, volume=1),
        ]
        out = fanout.on_base_closed_batch(base_series_id=base_series_id, candles=base)
        derived_id = to_derived_series_id(base_series_id, timeframe="5m")
        self.assertIn(derived_id, out)
        self.assertEqual(len(out[derived_id]), 1)
        c = out[derived_id][0]
        self.assertEqual(int(c.candle_time), 0)
        self.assertAlmostEqual(float(c.open), 1.0)
        self.assertAlmostEqual(float(c.close), 2.3)
        self.assertAlmostEqual(float(c.high), 3.0)
        self.assertAlmostEqual(float(c.low), 0.5)
        self.assertAlmostEqual(float(c.volume), 5.0)

        # Dedup: replay same minutes should not emit another 5m candle.
        out2 = fanout.on_base_closed_batch(base_series_id=base_series_id, candles=base)
        self.assertEqual(out2, {})


if __name__ == "__main__":
    unittest.main()

