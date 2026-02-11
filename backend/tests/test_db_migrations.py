from __future__ import annotations

import sqlite3

from backend.app.factor_store import FactorStore
from backend.app.overlay_store import OverlayStore
from backend.app.store import CandleStore


def _read_migration_rows(db_path) -> list[tuple[str, int]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT namespace, version
            FROM tc_schema_migrations
            ORDER BY namespace ASC, version ASC
            """
        ).fetchall()
    return [(str(row["namespace"]), int(row["version"])) for row in rows]


def test_schema_migrations_create_namespace_versions(tmp_path) -> None:
    db_path = tmp_path / "market.db"
    series_id = "binance:futures:BTC/USDT:1m"

    candle_store = CandleStore(db_path=db_path)
    factor_store = FactorStore(db_path=db_path)
    overlay_store = OverlayStore(db_path=db_path)

    assert candle_store.head_time(series_id) is None
    assert factor_store.head_time(series_id) is None
    assert overlay_store.head_time(series_id) is None

    assert _read_migration_rows(db_path) == [
        ("candles", 1),
        ("factor", 1),
        ("overlay", 1),
    ]


def test_schema_migrations_are_idempotent_when_reopening_store(tmp_path) -> None:
    db_path = tmp_path / "market.db"
    series_id = "binance:futures:BTC/USDT:1m"

    first = CandleStore(db_path=db_path)
    second = CandleStore(db_path=db_path)

    assert first.head_time(series_id) is None
    before = _read_migration_rows(db_path)
    assert before == [("candles", 1)]

    assert second.head_time(series_id) is None
    after = _read_migration_rows(db_path)
    assert after == before
