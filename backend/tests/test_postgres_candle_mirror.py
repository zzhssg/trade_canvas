from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.schemas import CandleClosed
from backend.app.storage.postgres_candle_mirror import PostgresCandleMirror


@dataclass
class _FakeConn:
    delete_rowcount: int = 0

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: Any | None = None) -> Any:
        compact_sql = " ".join(str(sql).split())
        self.calls.append((compact_sql, params))
        if compact_sql.startswith("DELETE "):
            return SimpleNamespace(rowcount=self.delete_rowcount)
        return SimpleNamespace(rowcount=1)

    def commit(self) -> None:
        self.commits += 1


class _FakePool:
    def __init__(self, *, delete_rowcount: int = 0) -> None:
        self.conn = _FakeConn(delete_rowcount=delete_rowcount)

    def connect(self):
        conn = self.conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


def _candle(t: int, close: float) -> CandleClosed:
    return CandleClosed(
        candle_time=int(t),
        open=float(close),
        high=float(close),
        low=float(close),
        close=float(close),
        volume=1.0,
    )


def test_upsert_closed_batch_executes_insert_per_candle_and_commits_once() -> None:
    pool = _FakePool()
    mirror = PostgresCandleMirror(pool=pool, schema="trade_canvas")
    candles = [_candle(100, 1.0), _candle(160, 2.0)]

    affected = mirror.upsert_closed_batch(series_id="s1", candles=candles)

    assert affected == 2
    assert pool.conn.commits == 1
    assert len(pool.conn.calls) == 2
    first_sql, first_params = pool.conn.calls[0]
    assert "INSERT INTO trade_canvas.candles" in first_sql
    assert first_params == ("s1", 100, 1.0, 1.0, 1.0, 1.0, 1.0)


def test_delete_closed_times_dedupes_and_returns_rowcount() -> None:
    pool = _FakePool(delete_rowcount=2)
    mirror = PostgresCandleMirror(pool=pool, schema="trade_canvas")

    deleted = mirror.delete_closed_times(series_id="s1", candle_times=[160, -1, 100, 160, 0])

    assert deleted == 2
    assert pool.conn.commits == 1
    assert len(pool.conn.calls) == 1
    sql, params = pool.conn.calls[0]
    assert "DELETE FROM trade_canvas.candles" in sql
    assert params == ["s1", 100, 160]


def test_upsert_closed_batch_skips_empty_input() -> None:
    pool = _FakePool()
    mirror = PostgresCandleMirror(pool=pool, schema="trade_canvas")

    affected = mirror.upsert_closed_batch(series_id="s1", candles=[])

    assert affected == 0
    assert pool.conn.calls == []
    assert pool.conn.commits == 0


def test_postgres_candle_mirror_rejects_invalid_schema_name() -> None:
    with pytest.raises(ValueError, match="postgres_schema_invalid"):
        PostgresCandleMirror(pool=_FakePool(), schema="trade-canvas")
