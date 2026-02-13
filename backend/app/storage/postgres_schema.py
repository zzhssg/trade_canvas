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
    factor_series_state_table = f"{schema_name}.factor_series_state"
    factor_events_table = f"{schema_name}.factor_events"
    factor_head_snapshots_table = f"{schema_name}.factor_head_snapshots"
    factor_fingerprint_table = f"{schema_name}.factor_series_fingerprint"
    overlay_series_state_table = f"{schema_name}.overlay_series_state"
    overlay_versions_table = f"{schema_name}.overlay_instruction_versions"
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
            CREATE TABLE IF NOT EXISTS {factor_series_state_table} (
              series_id TEXT PRIMARY KEY,
              head_time BIGINT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {factor_events_table} (
              id BIGSERIAL PRIMARY KEY,
              series_id TEXT NOT NULL,
              factor_name TEXT NOT NULL,
              candle_time BIGINT NOT NULL,
              kind TEXT NOT NULL,
              event_key TEXT NOT NULL,
              payload_json JSONB NOT NULL,
              created_at_ms BIGINT NOT NULL,
              UNIQUE (series_id, factor_name, event_key)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {factor_head_snapshots_table} (
              id BIGSERIAL PRIMARY KEY,
              series_id TEXT NOT NULL,
              factor_name TEXT NOT NULL,
              candle_time BIGINT NOT NULL,
              seq BIGINT NOT NULL,
              head_json JSONB NOT NULL,
              created_at_ms BIGINT NOT NULL,
              UNIQUE (series_id, factor_name, candle_time, seq)
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {factor_fingerprint_table} (
              series_id TEXT PRIMARY KEY,
              fingerprint TEXT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            );
            """,
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_factor_events_series_time ON {factor_events_table}(series_id, candle_time);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_factor_events_series_factor_time ON {factor_events_table}(series_id, factor_name, candle_time);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_factor_head_series_factor_time ON {factor_head_snapshots_table}(series_id, factor_name, candle_time);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_factor_head_series_time ON {factor_head_snapshots_table}(series_id, candle_time);",
            f"""
            CREATE TABLE IF NOT EXISTS {overlay_series_state_table} (
              series_id TEXT PRIMARY KEY,
              head_time BIGINT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            );
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {overlay_versions_table} (
              version_id BIGSERIAL PRIMARY KEY,
              series_id TEXT NOT NULL,
              instruction_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              visible_time BIGINT NOT NULL,
              def_json JSONB NOT NULL,
              created_at_ms BIGINT NOT NULL
            );
            """,
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_overlay_versions_series_version ON {overlay_versions_table}(series_id, version_id);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_overlay_versions_series_visible ON {overlay_versions_table}(series_id, visible_time);",
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
