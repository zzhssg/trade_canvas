from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from backend.app.data_reconcile_service import DataReconcileService
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class _PgSqliteConnection:
    def __init__(self, conn: sqlite3.Connection, *, table_name: str) -> None:
        self._conn = conn
        self._table_name = table_name

    def execute(self, sql: str, params: Any | None = None) -> Any:
        normalized_sql = str(sql).replace(self._table_name, "candles").replace("%s", "?")
        return self._conn.execute(normalized_sql, tuple(params or ()))

    def close(self) -> None:
        self._conn.close()


class _PgSqlitePool:
    def __init__(self, *, db_path: Path, schema: str) -> None:
        self._db_path = db_path
        self._table_name = f"{schema}.candles"

    def connect(self):
        raw_conn = sqlite3.connect(self._db_path)
        raw_conn.row_factory = sqlite3.Row
        wrapped = _PgSqliteConnection(raw_conn, table_name=self._table_name)

        class _Ctx:
            def __enter__(self):
                return wrapped

            def __exit__(self, exc_type, exc, tb):
                wrapped.close()
                return False

        return _Ctx()


def _create_pg_like_sqlite(*, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()


def _upsert_pg_like(*, db_path: Path, series_id: str, candle: CandleClosed) -> None:
    conn = sqlite3.connect(db_path)
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
    conn.close()


def _candle(t: int, close: float) -> CandleClosed:
    return CandleClosed(
        candle_time=int(t),
        open=float(close),
        high=float(close),
        low=float(close),
        close=float(close),
        volume=1.0,
    )


def test_data_reconcile_service_match_when_sqlite_and_pg_are_aligned() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sqlite_store = CandleStore(db_path=root / "sqlite.db")
        pg_db_path = root / "pg.db"
        _create_pg_like_sqlite(db_path=pg_db_path)
        series_id = "binance:futures:BTC/USDT:1m"
        for candle in (_candle(100, 1.0), _candle(160, 2.0)):
            sqlite_store.upsert_closed(series_id, candle)
            _upsert_pg_like(db_path=pg_db_path, series_id=series_id, candle=candle)

        service = DataReconcileService(
            sqlite_store=sqlite_store,
            pg_pool=_PgSqlitePool(db_path=pg_db_path, schema="trade_canvas"),  # type: ignore[arg-type]
            pg_schema="trade_canvas",
        )
        snapshot = service.reconcile_series(series_id=series_id)

        assert snapshot.series_id == series_id
        assert snapshot.range_start == 100
        assert snapshot.range_end == 160
        assert snapshot.sqlite.count == 2
        assert snapshot.postgres.count == 2
        assert snapshot.diff.match is True


def test_data_reconcile_service_detects_drift_on_head_and_checksum() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sqlite_store = CandleStore(db_path=root / "sqlite.db")
        pg_db_path = root / "pg.db"
        _create_pg_like_sqlite(db_path=pg_db_path)
        series_id = "binance:futures:BTC/USDT:1m"

        sqlite_store.upsert_closed(series_id, _candle(100, 1.0))
        sqlite_store.upsert_closed(series_id, _candle(160, 2.0))
        _upsert_pg_like(db_path=pg_db_path, series_id=series_id, candle=_candle(100, 1.0))
        _upsert_pg_like(db_path=pg_db_path, series_id=series_id, candle=_candle(220, 9.0))

        service = DataReconcileService(
            sqlite_store=sqlite_store,
            pg_pool=_PgSqlitePool(db_path=pg_db_path, schema="trade_canvas"),  # type: ignore[arg-type]
            pg_schema="trade_canvas",
        )
        snapshot = service.reconcile_series(series_id=series_id)

        assert snapshot.sqlite.head_time == 160
        assert snapshot.postgres.head_time == 220
        assert snapshot.diff.head_match is False
        assert snapshot.diff.checksum_match is False
        assert snapshot.diff.match is False


def test_data_reconcile_service_rejects_invalid_range() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sqlite_store = CandleStore(db_path=root / "sqlite.db")
        pg_db_path = root / "pg.db"
        _create_pg_like_sqlite(db_path=pg_db_path)
        service = DataReconcileService(
            sqlite_store=sqlite_store,
            pg_pool=_PgSqlitePool(db_path=pg_db_path, schema="trade_canvas"),  # type: ignore[arg-type]
            pg_schema="trade_canvas",
        )

        with pytest.raises(ValueError, match="reconcile_range_invalid"):
            service.reconcile_series(
                series_id="binance:futures:BTC/USDT:1m",
                start_time=200,
                end_time=100,
            )
