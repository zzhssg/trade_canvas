from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from typing import Any

from ..overlay.store import OverlayInstructionVersionRow
from .contracts import DbConnection
from .postgres_common import (
    json_load,
    normalize_identifier,
    query_series_head_time,
    row_get,
    upsert_series_head_time,
)
from .postgres_pool import PostgresPool


class PostgresOverlayRepository:
    _pool: PostgresPool
    _schema: str
    _series_state_table: str
    _versions_table: str

    def __init__(self, *, pool: PostgresPool, schema: str) -> None:
        object.__setattr__(self, "_pool", pool)
        schema_name = normalize_identifier(schema, key="schema")
        object.__setattr__(self, "_schema", schema_name)
        object.__setattr__(self, "_series_state_table", f"{schema_name}.overlay_series_state")
        object.__setattr__(self, "_versions_table", f"{schema_name}.overlay_instruction_versions")

    def connect(self) -> AbstractContextManager[DbConnection]:
        return self._pool.connect()

    def upsert_head_time_in_conn(self, conn: DbConnection, *, series_id: str, head_time: int) -> None:
        upsert_series_head_time(
            conn,
            series_state_table=self._series_state_table,
            series_id=series_id,
            head_time=head_time,
        )

    def clear_series_in_conn(self, conn: DbConnection, *, series_id: str) -> None:
        sid = str(series_id)
        conn.execute(f"DELETE FROM {self._versions_table} WHERE series_id = %s", (sid,))
        conn.execute(f"DELETE FROM {self._series_state_table} WHERE series_id = %s", (sid,))

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            return query_series_head_time(
                conn,
                series_state_table=self._series_state_table,
                series_id=series_id,
            )

    def last_version_id(self, series_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT MAX(version_id) AS v FROM {self._versions_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        if row is None:
            return 0
        value = row_get(row, index=0, key="v")
        return 0 if value is None else int(value)

    def insert_instruction_version_in_conn(
        self,
        conn: DbConnection,
        *,
        series_id: str,
        instruction_id: str,
        kind: str,
        visible_time: int,
        payload: dict[str, Any],
    ) -> int:
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
        return int(row_get(row, index=0, key="version_id"))

    def get_latest_defs_up_to_time(
        self,
        *,
        series_id: str,
        up_to_time: int,
    ) -> list[OverlayInstructionVersionRow]:
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
    ) -> list[OverlayInstructionVersionRow]:
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
    ) -> list[OverlayInstructionVersionRow]:
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
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self.get_latest_def_for_instruction_in_conn(
                conn,
                series_id=series_id,
                instruction_id=instruction_id,
            )

    def get_latest_def_for_instruction_in_conn(
        self,
        conn: DbConnection,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:
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
        payload = json_load(row_get(row, index=0, key="def_json"))
        return payload if payload else None

    @staticmethod
    def _decode_overlay_rows(rows: list[Any]) -> list[OverlayInstructionVersionRow]:
        out: list[OverlayInstructionVersionRow] = []
        for row in rows:
            out.append(
                OverlayInstructionVersionRow(
                    version_id=int(row_get(row, index=0, key="version_id")),
                    series_id=str(row_get(row, index=1, key="series_id")),
                    instruction_id=str(row_get(row, index=2, key="instruction_id")),
                    kind=str(row_get(row, index=3, key="kind")),
                    visible_time=int(row_get(row, index=4, key="visible_time")),
                    payload=json_load(row_get(row, index=5, key="def_json")),
                )
            )
        return out
