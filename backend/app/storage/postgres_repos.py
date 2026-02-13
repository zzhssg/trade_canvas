from __future__ import annotations

import re
from contextlib import AbstractContextManager
from typing import Any

from ..core.schemas import CandleClosed
from .postgres_pool import PostgresPool


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_identifier(value: str, *, key: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError(f"postgres_{key}_required")
    if _IDENTIFIER.fullmatch(candidate) is None:
        raise ValueError(f"postgres_{key}_invalid:{candidate}")
    return candidate


def _row_get(row: Any, *, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (KeyError, IndexError):
            pass
    return row[index]


class PostgresCandleRepository:
    def __init__(self, *, pool: PostgresPool, schema: str) -> None:
        self._pool = pool
        self._schema = _normalize_identifier(schema, key="schema")
        self._table = f"{self._schema}.candles"

    def connect(self) -> AbstractContextManager[Any]:
        return self._pool.connect()

    def upsert_closed_in_conn(self, conn: Any, series_id: str, candle: CandleClosed) -> None:
        conn.execute(
            f"""
            INSERT INTO {self._table}(series_id, candle_time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(series_id, candle_time) DO UPDATE SET
              open=EXCLUDED.open,
              high=EXCLUDED.high,
              low=EXCLUDED.low,
              close=EXCLUDED.close,
              volume=EXCLUDED.volume
            """,
            (
                str(series_id),
                int(candle.candle_time),
                float(candle.open),
                float(candle.high),
                float(candle.low),
                float(candle.close),
                float(candle.volume),
            ),
        )

    def upsert_many_closed_in_conn(self, conn: Any, series_id: str, candles: list[CandleClosed]) -> None:
        if not candles:
            return
        for candle in candles:
            self.upsert_closed_in_conn(conn, series_id, candle)

    def upsert_many_closed(self, series_id: str, candles: list[CandleClosed]) -> None:
        if not candles:
            return
        with self.connect() as conn:
            self.upsert_many_closed_in_conn(conn, series_id, candles)
            conn.commit()

    def existing_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> set[int]:
        times = sorted({int(t) for t in candle_times if int(t) > 0})
        if not times:
            return set()
        placeholders = ",".join(["%s"] * len(times))
        cur = conn.execute(
            f"""
            SELECT candle_time
            FROM {self._table}
            WHERE series_id = %s AND candle_time IN ({placeholders})
            """,
            [str(series_id), *times],
        )
        rows = cur.fetchall()
        return {int(_row_get(row, index=0, key="candle_time")) for row in rows}

    def delete_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> int:
        times = sorted({int(t) for t in candle_times if int(t) > 0})
        if not times:
            return 0
        placeholders = ",".join(["%s"] * len(times))
        cur = conn.execute(
            f"DELETE FROM {self._table} WHERE series_id = %s AND candle_time IN ({placeholders})",
            [str(series_id), *times],
        )
        return int(getattr(cur, "rowcount", 0) or 0)

    def delete_closed_times(self, *, series_id: str, candle_times: list[int]) -> int:
        with self.connect() as conn:
            deleted = self.delete_closed_times_in_conn(
                conn,
                series_id=series_id,
                candle_times=candle_times,
            )
            conn.commit()
        return int(deleted)

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:
        with self.connect() as conn:
            self.upsert_closed_in_conn(conn, series_id, candle)
            conn.commit()

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT MAX(candle_time) AS head_time FROM {self._table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
            if row is None:
                return None
            value = _row_get(row, index=0, key="head_time")
            return None if value is None else int(value)

    def first_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT MIN(candle_time) AS first_time FROM {self._table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
            if row is None:
                return None
            value = _row_get(row, index=0, key="first_time")
            return None if value is None else int(value)

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(1) AS cnt
                FROM {self._table}
                WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
                """,
                (str(series_id), int(start_time), int(end_time)),
            ).fetchone()
            if row is None:
                return 0
            value = _row_get(row, index=0, key="cnt")
            return 0 if value is None else int(value)

    def trim_series_to_latest_n_in_conn(self, conn: Any, *, series_id: str, keep: int) -> int:
        keep_n = max(1, int(keep))
        row = conn.execute(
            f"""
            SELECT candle_time
            FROM {self._table}
            WHERE series_id = %s
            ORDER BY candle_time DESC
            LIMIT 1 OFFSET %s
            """,
            (str(series_id), int(keep_n - 1)),
        ).fetchone()
        if row is None:
            return 0
        cutoff = int(_row_get(row, index=0, key="candle_time"))
        cur = conn.execute(
            f"DELETE FROM {self._table} WHERE series_id = %s AND candle_time < %s",
            (str(series_id), int(cutoff)),
        )
        return int(getattr(cur, "rowcount", 0) or 0)

    def trim_series_to_latest_n(self, *, series_id: str, keep: int) -> int:
        with self.connect() as conn:
            trimmed = self.trim_series_to_latest_n_in_conn(
                conn,
                series_id=series_id,
                keep=int(keep),
            )
            conn.commit()
        return int(trimmed)

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT MAX(candle_time) AS t
                FROM {self._table}
                WHERE series_id = %s AND candle_time <= %s
                """,
                (str(series_id), int(at_time)),
            ).fetchone()
            if row is None:
                return None
            value = _row_get(row, index=0, key="t")
            return None if value is None else int(value)

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]:
        query_params: list[Any] = [str(series_id)]
        if since is None:
            sql = f"""
                SELECT candle_time, open, high, low, close, volume
                FROM {self._table}
                WHERE series_id = %s
                ORDER BY candle_time DESC
                LIMIT %s
            """
            query_params.append(int(limit))
        else:
            sql = f"""
                SELECT candle_time, open, high, low, close, volume
                FROM {self._table}
                WHERE series_id = %s AND candle_time > %s
                ORDER BY candle_time ASC
                LIMIT %s
            """
            query_params.extend([int(since), int(limit)])
        with self.connect() as conn:
            rows = conn.execute(sql, query_params).fetchall()
        candles = [
            CandleClosed(
                candle_time=int(_row_get(row, index=0, key="candle_time")),
                open=float(_row_get(row, index=1, key="open")),
                high=float(_row_get(row, index=2, key="high")),
                low=float(_row_get(row, index=3, key="low")),
                close=float(_row_get(row, index=4, key="close")),
                volume=float(_row_get(row, index=5, key="volume")),
            )
            for row in rows
        ]
        if since is None:
            candles.reverse()
        return candles

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT candle_time, open, high, low, close, volume
                FROM {self._table}
                WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
                ORDER BY candle_time ASC
                LIMIT %s
                """,
                (str(series_id), int(start_time), int(end_time), int(limit)),
            ).fetchall()
        return [
            CandleClosed(
                candle_time=int(_row_get(row, index=0, key="candle_time")),
                open=float(_row_get(row, index=1, key="open")),
                high=float(_row_get(row, index=2, key="high")),
                low=float(_row_get(row, index=3, key="low")),
                close=float(_row_get(row, index=4, key="close")),
                volume=float(_row_get(row, index=5, key="volume")),
            )
            for row in rows
        ]
