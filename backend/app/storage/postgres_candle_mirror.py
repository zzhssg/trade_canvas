from __future__ import annotations

import re
from contextlib import AbstractContextManager
from typing import Any, Protocol

from ..schemas import CandleClosed
from .postgres_pool import PostgresPool


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _ConnectionLike(Protocol):
    def execute(self, sql: str, params: Any | None = None) -> Any: ...

    def commit(self) -> None: ...


class _PoolLike(Protocol):
    def connect(self) -> AbstractContextManager[_ConnectionLike]: ...


class PostgresCandleMirror:
    """Best-effort shadow writer for candles dual-write."""

    def __init__(self, *, pool: PostgresPool | _PoolLike, schema: str) -> None:
        self._pool = pool
        self._schema = self._normalize_identifier(schema=schema)
        self._table = f"{self._schema}.candles"

    @staticmethod
    def _normalize_identifier(*, schema: str) -> str:
        candidate = str(schema or "").strip()
        if not candidate:
            raise ValueError("postgres_schema_required")
        if _IDENTIFIER.fullmatch(candidate) is None:
            raise ValueError(f"postgres_schema_invalid:{candidate}")
        return candidate

    def upsert_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> int:
        if not candles:
            return 0
        sql = (
            f"""
            INSERT INTO {self._table}(series_id, candle_time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(series_id, candle_time) DO UPDATE SET
              open=EXCLUDED.open,
              high=EXCLUDED.high,
              low=EXCLUDED.low,
              close=EXCLUDED.close,
              volume=EXCLUDED.volume
            """
        )
        with self._pool.connect() as conn:
            for candle in candles:
                conn.execute(
                    sql,
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
            conn.commit()
        return len(candles)

    def delete_closed_times(self, *, series_id: str, candle_times: list[int]) -> int:
        times = sorted({int(t) for t in candle_times if int(t) > 0})
        if not times:
            return 0
        placeholders = ",".join("%s" for _ in times)
        sql = f"DELETE FROM {self._table} WHERE series_id = %s AND candle_time IN ({placeholders})"
        with self._pool.connect() as conn:
            cur = conn.execute(sql, [str(series_id), *times])
            conn.commit()
        rowcount = getattr(cur, "rowcount", 0)
        return max(0, int(rowcount or 0))
