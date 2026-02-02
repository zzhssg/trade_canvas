from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trade_canvas.adapter import SingleSourceAdapter
from trade_canvas.kernel import SmaCrossKernel
from trade_canvas.store import SqliteStore
from trade_canvas.types import CandleClosed


def load_fixture(path: Path) -> list[CandleClosed]:
    candles: list[CandleClosed] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        candles.append(
            CandleClosed(
                symbol=obj["symbol"],
                timeframe=obj["timeframe"],
                open_time=int(obj["open_time"]),
                open=float(obj["open"]),
                high=float(obj["high"]),
                low=float(obj["low"]),
                close=float(obj["close"]),
                volume=float(obj["volume"]),
            )
        )
    return candles


class TestE2ESqlitePipeline(unittest.TestCase):
    def test_happy_path_alignment(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "klines_mock_BTCUSDT_1m_60.jsonl"
        candles = load_fixture(fixture)
        self.assertGreaterEqual(len(candles), 40)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "e2e.sqlite3"
            store = SqliteStore(db_path)
            conn = store.connect()
            try:
                store.init_schema(conn)
                kernel = SmaCrossKernel(store)

                for candle in candles:
                    store.upsert_candle(conn, candle=candle)
                    kernel.apply_closed(conn, candle)

                adapter = SingleSourceAdapter(store)
                res = adapter.get_latest(conn, symbol="BTC/USDT", timeframe="1m")
                self.assertTrue(res.ok, res.reason)
                self.assertIsNotNone(res.ledger)

                latest_candle_id = store.get_latest_candle_id(conn, symbol="BTC/USDT", timeframe="1m")
                self.assertEqual(res.ledger["candle_id"], latest_candle_id)

                # Find the first OPEN_LONG signal by scanning overlay events via "latest" call.
                # (Kernel only writes overlay marker when signal triggers.)
                entry = res.entry_marker
                if res.ledger["signal"] is not None:
                    # If latest candle is the signal candle, the marker must match candle_id.
                    self.assertIsNotNone(entry)
                    self.assertEqual(res.ledger["signal"]["candle_id"], entry.candle_id)

                # Determinism: rerun from scratch into a new db and compare the first entry candle_id.
                db_path2 = Path(tmpdir) / "e2e_2.sqlite3"
                store2 = SqliteStore(db_path2)
                conn2 = store2.connect()
                try:
                    store2.init_schema(conn2)
                    kernel2 = SmaCrossKernel(store2)
                    for candle in candles:
                        store2.upsert_candle(conn2, candle=candle)
                        kernel2.apply_closed(conn2, candle)
                    adapter2 = SingleSourceAdapter(store2)
                    res2 = adapter2.get_latest(conn2, symbol="BTC/USDT", timeframe="1m")
                    self.assertTrue(res2.ok, res2.reason)
                    self.assertEqual(res2.ledger["candle_id"], res.ledger["candle_id"])
                finally:
                    conn2.close()
            finally:
                conn.close()

    def test_fail_safe_mismatch(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "klines_mock_BTCUSDT_1m_60.jsonl"
        candles = load_fixture(fixture)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "e2e.sqlite3"
            store = SqliteStore(db_path)
            conn = store.connect()
            try:
                store.init_schema(conn)
                kernel = SmaCrossKernel(store)

                for candle in candles[:25]:
                    store.upsert_candle(conn, candle=candle)
                    kernel.apply_closed(conn, candle)

                # Tamper: create a candle row without running kernel (simulates out-of-sync consumer).
                last = candles[25]
                store.upsert_candle(conn, candle=last)
                conn.commit()

                adapter = SingleSourceAdapter(store)
                res = adapter.get_latest(conn, symbol="BTC/USDT", timeframe="1m")
                self.assertFalse(res.ok)
                self.assertEqual(res.reason, "candle_id_mismatch")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

