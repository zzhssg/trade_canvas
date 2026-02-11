from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.factor_store import FactorStore


class FactorHeadStoreTests(unittest.TestCase):
    def test_head_snapshot_seq_and_point_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "factor.db"
            store = FactorStore(db_path=db_path)
            with store.connect() as conn:
                seq0 = store.insert_head_snapshot_in_conn(
                    conn,
                    series_id="s",
                    factor_name="pen",
                    candle_time=100,
                    head={"candidate": {"x": 1}},
                )
                seq0_dup = store.insert_head_snapshot_in_conn(
                    conn,
                    series_id="s",
                    factor_name="pen",
                    candle_time=100,
                    head={"candidate": {"x": 1}},
                )
                seq1 = store.insert_head_snapshot_in_conn(
                    conn,
                    series_id="s",
                    factor_name="pen",
                    candle_time=100,
                    head={"candidate": {"x": 2}},
                )
                seq2 = store.insert_head_snapshot_in_conn(
                    conn,
                    series_id="s",
                    factor_name="pen",
                    candle_time=120,
                    head={},
                )
                conn.commit()

                self.assertEqual(seq0, 0)
                self.assertEqual(seq0_dup, 0)
                self.assertEqual(seq1, 1)
                self.assertEqual(seq2, 0)

                row_at_100 = store.get_head_at_or_before(series_id="s", factor_name="pen", candle_time=100)
                self.assertIsNotNone(row_at_100)
                assert row_at_100 is not None
                self.assertEqual(row_at_100.candle_time, 100)
                self.assertEqual(row_at_100.seq, 1)
                self.assertEqual(row_at_100.head.get("candidate", {}).get("x"), 2)

                row_at_110 = store.get_head_at_or_before(series_id="s", factor_name="pen", candle_time=110)
                self.assertIsNotNone(row_at_110)
                assert row_at_110 is not None
                self.assertEqual(row_at_110.candle_time, 100)
                self.assertEqual(row_at_110.seq, 1)

                row_at_130 = store.get_head_at_or_before(series_id="s", factor_name="pen", candle_time=130)
                self.assertIsNotNone(row_at_130)
                assert row_at_130 is not None
                self.assertEqual(row_at_130.candle_time, 120)
                self.assertEqual(row_at_130.seq, 0)

                count = conn.execute(
                    "SELECT COUNT(1) AS c FROM factor_head_snapshots WHERE series_id = ? AND factor_name = ?",
                    ("s", "pen"),
                ).fetchone()
                self.assertEqual(int(count["c"]), 3)


if __name__ == "__main__":
    unittest.main()
