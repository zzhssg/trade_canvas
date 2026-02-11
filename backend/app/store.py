from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .db_migrations import SqliteMigration, apply_migrations
from .schemas import CandleClosed
from .sqlite_util import connect as sqlite_connect


_schema_inited: set[str] = set()
_schema_lock = threading.Lock()


@dataclass(frozen=True)
class CandleStore:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite_connect(self.db_path)
        key = str(self.db_path)
        if key not in _schema_inited:
            with _schema_lock:
                if key not in _schema_inited:
                    apply_migrations(
                        conn,
                        namespace="candles",
                        migrations=self._schema_migrations(),
                    )
                    _schema_inited.add(key)
        return conn

    @staticmethod
    def _schema_statements() -> tuple[str, ...]:
        return (
            """
            CREATE TABLE IF NOT EXISTS candles (
              series_id TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              open REAL NOT NULL,
              high REAL NOT NULL,
              low REAL NOT NULL,
              close REAL NOT NULL,
              volume REAL NOT NULL,
              PRIMARY KEY (series_id, candle_time)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_candles_series_time ON candles(series_id, candle_time);",
        )

    @classmethod
    def _schema_migrations(cls) -> tuple[SqliteMigration, ...]:
        return (
            SqliteMigration(
                version=1,
                statements=cls._schema_statements(),
            ),
        )

    def upsert_closed_in_conn(self, conn: sqlite3.Connection, series_id: str, candle: CandleClosed) -> None:
        conn.execute(
            """
            INSERT INTO candles(series_id, candle_time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, candle_time) DO UPDATE SET
              open=excluded.open,
              high=excluded.high,
              low=excluded.low,
              close=excluded.close,
              volume=excluded.volume
            """,
            (
                series_id,
                candle.candle_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            ),
        )

    def upsert_many_closed_in_conn(self, conn: sqlite3.Connection, series_id: str, candles: list[CandleClosed]) -> None:
        if not candles:
            return
        conn.executemany(
            """
            INSERT INTO candles(series_id, candle_time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, candle_time) DO UPDATE SET
              open=excluded.open,
              high=excluded.high,
              low=excluded.low,
              close=excluded.close,
              volume=excluded.volume
            """,
            [
                (
                    series_id,
                    c.candle_time,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                )
                for c in candles
            ],
        )

    def existing_closed_times_in_conn(self, conn: sqlite3.Connection, *, series_id: str, candle_times: list[int]) -> set[int]:
        times = sorted({int(t) for t in candle_times if int(t) > 0})
        if not times:
            return set()
        placeholders = ",".join("?" for _ in times)
        rows = conn.execute(
            f"""
            SELECT candle_time
            FROM candles
            WHERE series_id = ? AND candle_time IN ({placeholders})
            """,
            [series_id, *times],
        ).fetchall()
        return {int(r["candle_time"]) for r in rows}

    def delete_closed_times_in_conn(self, conn: sqlite3.Connection, *, series_id: str, candle_times: list[int]) -> int:
        times = sorted({int(t) for t in candle_times if int(t) > 0})
        if not times:
            return 0
        placeholders = ",".join("?" for _ in times)
        cur = conn.execute(
            f"DELETE FROM candles WHERE series_id = ? AND candle_time IN ({placeholders})",
            [series_id, *times],
        )
        return int(cur.rowcount or 0)

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:
        with self.connect() as conn:
            self.upsert_closed_in_conn(conn, series_id, candle)
            conn.commit()

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(candle_time) AS head_time FROM candles WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return row["head_time"]

    def first_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MIN(candle_time) AS first_time FROM candles WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return row["first_time"]

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM candles
                WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
                """,
                (series_id, int(start_time), int(end_time)),
            ).fetchone()
            if row is None or row["cnt"] is None:
                return 0
            return int(row["cnt"])

    def trim_series_to_latest_n_in_conn(self, conn: sqlite3.Connection, *, series_id: str, keep: int) -> int:
        keep_n = max(1, int(keep))
        row = conn.execute(
            """
            SELECT candle_time
            FROM candles
            WHERE series_id = ?
            ORDER BY candle_time DESC
            LIMIT 1 OFFSET ?
            """,
            (series_id, int(keep_n - 1)),
        ).fetchone()
        if row is None:
            return 0
        cutoff = int(row["candle_time"])
        cur = conn.execute(
            "DELETE FROM candles WHERE series_id = ? AND candle_time < ?",
            (series_id, int(cutoff)),
        )
        return int(cur.rowcount or 0)

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
        """
        Return the greatest candle_time <= at_time (Unix seconds) for the series.
        """
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(candle_time) AS t
                FROM candles
                WHERE series_id = ? AND candle_time <= ?
                """,
                (series_id, int(at_time)),
            ).fetchone()
            if row is None:
                return None
            return row["t"]

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]:
        with self.connect() as conn:
            if since is None:
                rows = conn.execute(
                    """
                    SELECT candle_time, open, high, low, close, volume
                    FROM candles
                    WHERE series_id = ?
                    ORDER BY candle_time DESC
                    LIMIT ?
                    """,
                    (series_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = conn.execute(
                    """
                    SELECT candle_time, open, high, low, close, volume
                    FROM candles
                    WHERE series_id = ? AND candle_time > ?
                    ORDER BY candle_time ASC
                    LIMIT ?
                    """,
                    (series_id, since, limit),
                ).fetchall()
            return [CandleClosed(**dict(r)) for r in rows]

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        """
        Return candles with start_time <= candle_time <= end_time, ordered ascending.
        """
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT candle_time, open, high, low, close, volume
                FROM candles
                WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
                ORDER BY candle_time ASC
                LIMIT ?
                """,
                (series_id, int(start_time), int(end_time), int(limit)),
            ).fetchall()
        return [CandleClosed(**dict(r)) for r in rows]
