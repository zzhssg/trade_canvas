from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.app.storage.postgres_schema import build_postgres_bootstrap_sql, bootstrap_postgres_schema


@dataclass
class _FakeConn:
    statements: list[str]
    commits: int = 0

    def execute(self, sql: str) -> None:
        self.statements.append(str(sql).strip())

    def commit(self) -> None:
        self.commits += 1


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConn(statements=[])

    def connect(self):
        conn = self.conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


def test_build_postgres_bootstrap_sql_includes_timescale_and_state_tables() -> None:
    sql = build_postgres_bootstrap_sql(schema="trade_canvas", enable_timescale=True)
    joined = "\n".join(sql)
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in joined
    assert "CREATE TABLE IF NOT EXISTS trade_canvas.candles" in joined
    assert "CREATE TABLE IF NOT EXISTS trade_canvas.factor_series_state" in joined
    assert "CREATE TABLE IF NOT EXISTS trade_canvas.overlay_series_state" in joined
    assert "create_hypertable('trade_canvas.candles'" in joined


def test_bootstrap_postgres_schema_executes_all_statements_and_commits_once() -> None:
    pool = _FakePool()
    count = bootstrap_postgres_schema(pool=pool, schema="trade_canvas", enable_timescale=True)
    assert count == len(pool.conn.statements)
    assert pool.conn.commits == 1
    assert any("CREATE SCHEMA IF NOT EXISTS trade_canvas" in stmt for stmt in pool.conn.statements)


def test_build_postgres_bootstrap_sql_rejects_invalid_schema_name() -> None:
    with pytest.raises(ValueError, match="postgres_schema_invalid"):
        build_postgres_bootstrap_sql(schema="trade-canvas", enable_timescale=True)
