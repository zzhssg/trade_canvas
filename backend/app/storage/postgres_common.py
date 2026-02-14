from __future__ import annotations

import json
import re
import time
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_identifier(value: str, *, key: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError(f"postgres_{key}_required")
    if _IDENTIFIER.fullmatch(candidate) is None:
        raise ValueError(f"postgres_{key}_invalid:{candidate}")
    return candidate


def row_get(row: Any, *, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (KeyError, IndexError):
            pass
    return row[index]


def json_load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def upsert_series_head_time(
    conn: Any,
    *,
    series_state_table: str,
    series_id: str,
    head_time: int,
    updated_at_ms: int | None = None,
) -> None:
    now_ms = int(time.time() * 1000) if updated_at_ms is None else int(updated_at_ms)
    conn.execute(
        f"""
        INSERT INTO {series_state_table}(series_id, head_time, updated_at_ms)
        VALUES (%s, %s, %s)
        ON CONFLICT(series_id) DO UPDATE SET
          head_time=GREATEST({series_state_table}.head_time, EXCLUDED.head_time),
          updated_at_ms=EXCLUDED.updated_at_ms
        """,
        (str(series_id), int(head_time), now_ms),
    )


def query_series_head_time(
    conn: Any,
    *,
    series_state_table: str,
    series_id: str,
) -> int | None:
    row = conn.execute(
        f"SELECT head_time FROM {series_state_table} WHERE series_id = %s",
        (str(series_id),),
    ).fetchone()
    if row is None:
        return None
    value = row_get(row, index=0, key="head_time")
    return None if value is None else int(value)


__all__ = [
    "json_load",
    "normalize_identifier",
    "query_series_head_time",
    "row_get",
    "upsert_series_head_time",
]
