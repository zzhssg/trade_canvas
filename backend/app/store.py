from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .schemas import CandleClosed


@dataclass(frozen=True)
class CandleStore:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_schema(conn)
        return conn

    def ensure_schema(self, conn: sqlite3.Connection) -> None:
        self._ensure_schema(conn)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
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
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_series_time ON candles(series_id, candle_time);")
        conn.commit()

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
