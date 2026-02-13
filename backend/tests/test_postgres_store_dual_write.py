from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.schemas import CandleClosed
from backend.app.storage.dual_write_repos import DualWriteCandleRepository
from backend.app.storage.sqlite_repos import SqliteCandleRepository


class _FakeMirror:
    def __init__(self) -> None:
        self.head: dict[str, int] = {}
        self.calls: list[tuple[str, str, int]] = []

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:
        self.head[series_id] = max(int(candle.candle_time), int(self.head.get(series_id, 0)))
        self.calls.append(("upsert_closed", series_id, int(candle.candle_time)))

    def upsert_many_closed(self, series_id: str, candles: list[CandleClosed]) -> None:
        for candle in candles:
            self.upsert_closed(series_id, candle)

    def delete_closed_times(self, *, series_id: str, candle_times: list[int]) -> int:
        deleted = 0
        for t in candle_times:
            if int(self.head.get(series_id, 0)) == int(t):
                self.head[series_id] = 0
                deleted += 1
        self.calls.append(("delete_closed_times", series_id, deleted))
        return int(deleted)

    def trim_series_to_latest_n(self, *, series_id: str, keep: int) -> int:  # noqa: ARG002
        self.calls.append(("trim_series_to_latest_n", series_id, int(keep)))
        return 0

    def head_time(self, series_id: str) -> int | None:
        head = int(self.head.get(series_id, 0))
        return head if head > 0 else None

    def first_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return None

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:  # noqa: ARG002
        return 0

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # noqa: ARG002
        return self.head_time(series_id)

    def get_closed(self, series_id: str, *, since: int | None, limit: int):  # noqa: ANN001, ARG002
        _ = since, limit
        head = self.head_time(series_id)
        if head is None:
            return []
        return [CandleClosed(candle_time=head, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)]

    def get_closed_between_times(self, series_id: str, *, start_time: int, end_time: int, limit: int = 20000):  # noqa: ANN001, ARG002
        _ = start_time, end_time, limit
        return self.get_closed(series_id, since=None, limit=1)


class PostgresDualWriteStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        self.series_id = "binance:spot:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_dual_write_mirrors_closed_batch(self) -> None:
        primary = SqliteCandleRepository(db_path=self.db_path)
        mirror = _FakeMirror()
        store = DualWriteCandleRepository(
            primary=primary,
            mirror=mirror,
            enable_dual_write=True,
            enable_pg_read=False,
        )

        candles = [
            CandleClosed(candle_time=100, open=1, high=2, low=0.5, close=1.5, volume=10),
            CandleClosed(candle_time=160, open=1.5, high=2.5, low=1.0, close=2.0, volume=11),
        ]
        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, self.series_id, candles)
            conn.commit()

        self.assertEqual(store.head_time(self.series_id), 160)
        self.assertEqual(mirror.head_time(self.series_id), 160)
        self.assertIn(("upsert_closed", self.series_id, 100), mirror.calls)
        self.assertIn(("upsert_closed", self.series_id, 160), mirror.calls)

    def test_pg_read_prefers_mirror_head_when_enabled(self) -> None:
        primary = SqliteCandleRepository(db_path=self.db_path)
        primary.upsert_closed(
            self.series_id,
            CandleClosed(candle_time=100, open=1, high=2, low=0.5, close=1.5, volume=10),
        )
        mirror = _FakeMirror()
        mirror.upsert_closed(
            self.series_id,
            CandleClosed(candle_time=220, open=1, high=2, low=0.5, close=1.5, volume=10),
        )
        store = DualWriteCandleRepository(
            primary=primary,
            mirror=mirror,
            enable_dual_write=False,
            enable_pg_read=True,
        )

        self.assertEqual(store.head_time(self.series_id), 220)

    def test_dual_write_delete_propagates_to_mirror(self) -> None:
        primary = SqliteCandleRepository(db_path=self.db_path)
        mirror = _FakeMirror()
        store = DualWriteCandleRepository(
            primary=primary,
            mirror=mirror,
            enable_dual_write=True,
            enable_pg_read=False,
        )
        candle = CandleClosed(candle_time=300, open=1, high=2, low=0.5, close=1.5, volume=10)
        store.upsert_closed(self.series_id, candle)

        with store.connect() as conn:
            deleted = store.delete_closed_times_in_conn(
                conn,
                series_id=self.series_id,
                candle_times=[300],
            )
            conn.commit()
        self.assertEqual(deleted, 1)
        self.assertIn(("delete_closed_times", self.series_id, 1), mirror.calls)


if __name__ == "__main__":
    unittest.main()
