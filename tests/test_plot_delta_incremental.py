from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_canvas.kernel import SmaCrossKernel
from trade_canvas.plot_adapter import PlotCursor, PlotDeltaAdapter
from trade_canvas.store import SqliteStore
from trade_canvas.types import CandleClosed


def _candle(*, symbol: str, timeframe: str, t: int, close: float) -> CandleClosed:
    # Keep OHLC consistent for test simplicity.
    return CandleClosed(
        symbol=symbol,
        timeframe=timeframe,
        open_time=t,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


class TestPlotDeltaIncremental(unittest.TestCase):
    def test_plot_delta_incremental_points_and_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "plot.sqlite3"
            store = SqliteStore(db_path)
            conn = store.connect()
            try:
                store.init_schema(conn)
                kernel = SmaCrossKernel(store, fast=2, slow=3)
                adapter = PlotDeltaAdapter(store)

                symbol = "BTC/USDT"
                timeframe = "1m"

                # Warmup: 3 candles at price=1 (slow SMA becomes available at t=3).
                candles = [
                    _candle(symbol=symbol, timeframe=timeframe, t=1, close=1),
                    _candle(symbol=symbol, timeframe=timeframe, t=2, close=1),
                    _candle(symbol=symbol, timeframe=timeframe, t=3, close=1),
                ]
                for c in candles:
                    store.upsert_candle(conn, candle=c)
                    kernel.apply_closed(conn, c)

                res1 = adapter.get_delta(
                    conn,
                    symbol=symbol,
                    timeframe=timeframe,
                    feature_keys=["sma_2", "sma_3"],
                    cursor=None,
                )
                self.assertTrue(res1.ok, res1.reason)
                self.assertEqual(res1.to_candle_time, 3)
                self.assertIsNotNone(res1.next_cursor)
                self.assertEqual(res1.next_cursor.candle_time, 3)
                self.assertEqual(res1.overlay_events, [])
                self.assertGreaterEqual(len(res1.lines.get("sma_2", [])), 1)
                self.assertGreaterEqual(len(res1.lines.get("sma_3", [])), 1)

                # Next candle spikes, triggering crossover signal and a marker.
                c4 = _candle(symbol=symbol, timeframe=timeframe, t=4, close=10)
                store.upsert_candle(conn, candle=c4)
                kernel.apply_closed(conn, c4)

                res2 = adapter.get_delta(
                    conn,
                    symbol=symbol,
                    timeframe=timeframe,
                    feature_keys=["sma_2", "sma_3"],
                    cursor=res1.next_cursor,
                )
                self.assertTrue(res2.ok, res2.reason)
                self.assertEqual(res2.to_candle_time, 4)
                self.assertIsNotNone(res2.next_cursor)
                self.assertEqual(res2.next_cursor.candle_time, 4)

                # Incremental: only one new point per line for one new candle.
                self.assertLessEqual(len(res2.lines.get("sma_2", [])), 1)
                self.assertLessEqual(len(res2.lines.get("sma_3", [])), 1)
                self.assertEqual(len(res2.overlay_events), 1)
                self.assertEqual(res2.overlay_events[0].kind, "signal.entry")

                # Idempotent: calling again with the advanced cursor yields no more deltas.
                res3 = adapter.get_delta(
                    conn,
                    symbol=symbol,
                    timeframe=timeframe,
                    feature_keys=["sma_2", "sma_3"],
                    cursor=res2.next_cursor,
                )
                self.assertTrue(res3.ok, res3.reason)
                self.assertEqual(res3.lines.get("sma_2", []), [])
                self.assertEqual(res3.lines.get("sma_3", []), [])
                self.assertEqual(res3.overlay_events, [])
            finally:
                conn.close()

    def test_plot_delta_fail_safe_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "plot.sqlite3"
            store = SqliteStore(db_path)
            conn = store.connect()
            try:
                store.init_schema(conn)
                kernel = SmaCrossKernel(store, fast=2, slow=3)
                adapter = PlotDeltaAdapter(store)

                symbol = "BTC/USDT"
                timeframe = "1m"

                for c in [
                    _candle(symbol=symbol, timeframe=timeframe, t=1, close=1),
                    _candle(symbol=symbol, timeframe=timeframe, t=2, close=1),
                    _candle(symbol=symbol, timeframe=timeframe, t=3, close=1),
                ]:
                    store.upsert_candle(conn, candle=c)
                    kernel.apply_closed(conn, c)

                # Tamper: insert a candle without running the kernel.
                last = _candle(symbol=symbol, timeframe=timeframe, t=4, close=2)
                store.upsert_candle(conn, candle=last)
                conn.commit()

                res = adapter.get_delta(
                    conn,
                    symbol=symbol,
                    timeframe=timeframe,
                    feature_keys=["sma_2", "sma_3"],
                    cursor=PlotCursor(candle_time=3, overlay_event_id=None),
                )
                self.assertFalse(res.ok)
                self.assertEqual(res.reason, "candle_id_mismatch")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

