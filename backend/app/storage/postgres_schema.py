from __future__ import annotations

import re
from typing import Sequence

from .postgres_pool import PostgresPool


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_identifier(value: str, *, key: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError(f"postgres_{key}_required")
    if _IDENTIFIER.fullmatch(candidate) is None:
        raise ValueError(f"postgres_{key}_invalid:{candidate}")
    return candidate


def build_postgres_bootstrap_sql(*, schema: str, enable_timescale: bool) -> tuple[str, ...]:
    schema_name = _normalize_identifier(schema, key="schema")
    candles_table = f"{schema_name}.candles"
    statements: list[str] = []
    if bool(enable_timescale):
        statements.append("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    statements.extend(
        (
            f"CREATE SCHEMA IF NOT EXISTS {schema_name};",
            f"""
            CREATE TABLE IF NOT EXISTS {candles_table} (
              series_id TEXT NOT NULL,
              candle_time BIGINT NOT NULL,
              open DOUBLE PRECISION NOT NULL,
              high DOUBLE PRECISION NOT NULL,
              low DOUBLE PRECISION NOT NULL,
              close DOUBLE PRECISION NOT NULL,
              volume DOUBLE PRECISION NOT NULL,
              PRIMARY KEY (series_id, candle_time)
            );
            """,
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_candles_series_time ON {candles_table}(series_id, candle_time);",
            f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.factor_series_state (
              series_id TEXT PRIMARY KEY,
              head_time BIGINT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.overlay_series_state (
              series_id TEXT PRIMARY KEY,
              head_time BIGINT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            );
            """,
        )
    )
    if bool(enable_timescale):
        statements.append(
            f"SELECT create_hypertable('{candles_table}', 'candle_time', if_not_exists => TRUE, migrate_data => TRUE);"
        )
    return tuple(statements)


def bootstrap_postgres_schema(
    *,
    pool: PostgresPool,
    schema: str,
    enable_timescale: bool = True,
) -> int:
    sql: Sequence[str] = build_postgres_bootstrap_sql(
        schema=schema,
        enable_timescale=bool(enable_timescale),
    )
    with pool.connect() as conn:
        for stmt in sql:
            conn.execute(stmt)
        conn.commit()
    return len(sql)
