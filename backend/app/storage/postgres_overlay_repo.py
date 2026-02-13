from __future__ import annotations

import json
import re
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from ..overlay.store import OverlayInstructionVersionRow, OverlayStore
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


def _json_load(value: Any) -> dict[str, Any]:
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


class PostgresOverlayRepository(OverlayStore):
    _pool: PostgresPool
    _schema: str
    _series_state_table: str
    _versions_table: str

    def __init__(self, *, pool: PostgresPool, schema: str) -> None:
        super().__init__(db_path=Path("backend/data/postgres_overlay_store_unused.db"))
        object.__setattr__(self, "_pool", pool)
        schema_name = _normalize_identifier(schema, key="schema")
        object.__setattr__(self, "_schema", schema_name)
        object.__setattr__(self, "_series_state_table", f"{schema_name}.overlay_series_state")
        object.__setattr__(self, "_versions_table", f"{schema_name}.overlay_instruction_versions")

    def connect(self) -> AbstractContextManager[Any]:  # type: ignore[override]
        return self._pool.connect()

    def upsert_head_time_in_conn(self, conn: Any, *, series_id: str, head_time: int) -> None:  # type: ignore[override]
        now_ms = int(time.time() * 1000)
        conn.execute(
            f"""
            INSERT INTO {self._series_state_table}(series_id, head_time, updated_at_ms)
            VALUES (%s, %s, %s)
            ON CONFLICT(series_id) DO UPDATE SET
              head_time=GREATEST({self._series_state_table}.head_time, EXCLUDED.head_time),
              updated_at_ms=EXCLUDED.updated_at_ms
            """,
            (str(series_id), int(head_time), now_ms),
        )

    def clear_series_in_conn(self, conn: Any, *, series_id: str) -> None:  # type: ignore[override]
        sid = str(series_id)
        conn.execute(f"DELETE FROM {self._versions_table} WHERE series_id = %s", (sid,))
        conn.execute(f"DELETE FROM {self._series_state_table} WHERE series_id = %s", (sid,))

    def head_time(self, series_id: str) -> int | None:  # type: ignore[override]
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT head_time FROM {self._series_state_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        if row is None:
            return None
        value = _row_get(row, index=0, key="head_time")
        return None if value is None else int(value)

    def last_version_id(self, series_id: str) -> int:  # type: ignore[override]
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT MAX(version_id) AS v FROM {self._versions_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        if row is None:
            return 0
        value = _row_get(row, index=0, key="v")
        return 0 if value is None else int(value)

    def insert_instruction_version_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        instruction_id: str,
        kind: str,
        visible_time: int,
        payload: dict[str, Any],
    ) -> int:  # type: ignore[override]
        now_ms = int(time.time() * 1000)
        row = conn.execute(
            f"""
            INSERT INTO {self._versions_table}(series_id, instruction_id, kind, visible_time, def_json, created_at_ms)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING version_id
            """,
            (
                str(series_id),
                str(instruction_id),
                str(kind),
                int(visible_time),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                now_ms,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("overlay_instruction_versions_insert_missing_rowid")
        return int(_row_get(row, index=0, key="version_id"))

    def get_latest_defs_up_to_time(
        self,
        *,
        series_id: str,
        up_to_time: int,
    ) -> list[OverlayInstructionVersionRow]:  # type: ignore[override]
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT v.version_id, v.series_id, v.instruction_id, v.kind, v.visible_time, v.def_json
                FROM {self._versions_table} v
                JOIN (
                  SELECT instruction_id, MAX(version_id) AS max_id
                  FROM {self._versions_table}
                  WHERE series_id = %s AND visible_time <= %s
                  GROUP BY instruction_id
                ) m
                ON v.instruction_id = m.instruction_id AND v.version_id = m.max_id
                WHERE v.series_id = %s
                """,
                (str(series_id), int(up_to_time), str(series_id)),
            ).fetchall()
        return self._decode_overlay_rows(rows)

    def get_patch_after_version(
        self,
        *,
        series_id: str,
        after_version_id: int,
        up_to_time: int,
        limit: int = 50000,
    ) -> list[OverlayInstructionVersionRow]:  # type: ignore[override]
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT version_id, series_id, instruction_id, kind, visible_time, def_json
                FROM {self._versions_table}
                WHERE series_id = %s AND version_id > %s AND visible_time <= %s
                ORDER BY version_id ASC
                LIMIT %s
                """,
                (str(series_id), int(after_version_id), int(up_to_time), int(limit)),
            ).fetchall()
        return self._decode_overlay_rows(rows)

    def get_versions_between_times(
        self,
        *,
        series_id: str,
        start_visible_time: int,
        end_visible_time: int,
        limit: int = 200000,
    ) -> list[OverlayInstructionVersionRow]:  # type: ignore[override]
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT version_id, series_id, instruction_id, kind, visible_time, def_json
                FROM {self._versions_table}
                WHERE series_id = %s AND visible_time >= %s AND visible_time <= %s
                ORDER BY visible_time ASC, version_id ASC
                LIMIT %s
                """,
                (str(series_id), int(start_visible_time), int(end_visible_time), int(limit)),
            ).fetchall()
        return self._decode_overlay_rows(rows)

    def get_latest_def_for_instruction(
        self,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:  # type: ignore[override]
        with self.connect() as conn:
            return self.get_latest_def_for_instruction_in_conn(
                conn,
                series_id=series_id,
                instruction_id=instruction_id,
            )

    def get_latest_def_for_instruction_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:  # type: ignore[override]
        row = conn.execute(
            f"""
            SELECT def_json
            FROM {self._versions_table}
            WHERE series_id = %s AND instruction_id = %s
            ORDER BY version_id DESC
            LIMIT 1
            """,
            (str(series_id), str(instruction_id)),
        ).fetchone()
        if row is None:
            return None
        payload = _json_load(_row_get(row, index=0, key="def_json"))
        return payload if payload else None

    @staticmethod
    def _decode_overlay_rows(rows: list[Any]) -> list[OverlayInstructionVersionRow]:
        out: list[OverlayInstructionVersionRow] = []
        for row in rows:
            out.append(
                OverlayInstructionVersionRow(
                    version_id=int(_row_get(row, index=0, key="version_id")),
                    series_id=str(_row_get(row, index=1, key="series_id")),
                    instruction_id=str(_row_get(row, index=2, key="instruction_id")),
                    kind=str(_row_get(row, index=3, key="kind")),
                    visible_time=int(_row_get(row, index=4, key="visible_time")),
                    payload=_json_load(_row_get(row, index=5, key="def_json")),
                )
            )
        return out
