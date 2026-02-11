from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SqliteMigration:
    version: int
    statements: tuple[str, ...]


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tc_schema_migrations (
          namespace TEXT NOT NULL,
          version INTEGER NOT NULL,
          applied_at_ms INTEGER NOT NULL,
          PRIMARY KEY (namespace, version)
        )
        """
    )


def _normalize_migrations(*, migrations: tuple[SqliteMigration, ...]) -> tuple[SqliteMigration, ...]:
    unique: dict[int, SqliteMigration] = {}
    for migration in migrations:
        version = int(migration.version)
        if version <= 0:
            raise ValueError(f"sqlite_migration_invalid_version:{version}")
        if version in unique:
            raise ValueError(f"sqlite_migration_duplicate_version:{version}")
        unique[version] = SqliteMigration(
            version=version,
            statements=tuple(str(stmt) for stmt in migration.statements if str(stmt).strip()),
        )
    return tuple(unique[v] for v in sorted(unique.keys()))


def apply_migrations(
    conn: sqlite3.Connection,
    *,
    namespace: str,
    migrations: tuple[SqliteMigration, ...],
) -> int:
    normalized_namespace = str(namespace).strip()
    if not normalized_namespace:
        raise ValueError("sqlite_migration_namespace_required")

    ordered = _normalize_migrations(migrations=migrations)
    _ensure_migration_table(conn)
    row = conn.execute(
        "SELECT MAX(version) AS version FROM tc_schema_migrations WHERE namespace = ?",
        (normalized_namespace,),
    ).fetchone()
    current_version = int(row["version"]) if row is not None and row["version"] is not None else 0
    now_ms = int(time.time() * 1000)

    for migration in ordered:
        if int(migration.version) <= int(current_version):
            continue
        for statement in migration.statements:
            conn.execute(statement)
        conn.execute(
            """
            INSERT INTO tc_schema_migrations(namespace, version, applied_at_ms)
            VALUES (?, ?, ?)
            """,
            (normalized_namespace, int(migration.version), now_ms),
        )
        current_version = int(migration.version)

    conn.commit()
    return int(current_version)

