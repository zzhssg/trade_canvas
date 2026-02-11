from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .sqlite_util import connect as sqlite_connect


_schema_inited: set[str] = set()
_schema_lock = threading.Lock()


@dataclass(frozen=True)
class OverlayInstructionVersionRow:
    version_id: int
    series_id: str
    instruction_id: str
    kind: str
    visible_time: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class OverlayStore:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite_connect(self.db_path)
        key = str(self.db_path)
        if key not in _schema_inited:
            with _schema_lock:
                if key not in _schema_inited:
                    self._ensure_schema(conn)
                    _schema_inited.add(key)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS overlay_series_state (
              series_id TEXT PRIMARY KEY,
              head_time INTEGER NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS overlay_instruction_versions (
              version_id INTEGER PRIMARY KEY AUTOINCREMENT,
              series_id TEXT NOT NULL,
              instruction_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              visible_time INTEGER NOT NULL,
              def_json TEXT NOT NULL,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_overlay_versions_series_version ON overlay_instruction_versions(series_id, version_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_overlay_versions_series_visible ON overlay_instruction_versions(series_id, visible_time);"
        )
        conn.commit()

    def upsert_head_time_in_conn(self, conn: sqlite3.Connection, *, series_id: str, head_time: int) -> None:
        conn.execute(
            """
            INSERT INTO overlay_series_state(series_id, head_time, updated_at_ms)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
              head_time=MAX(head_time, excluded.head_time),
              updated_at_ms=excluded.updated_at_ms
            """,
            (series_id, int(head_time), int(time.time() * 1000)),
        )

    def clear_series_in_conn(self, conn: sqlite3.Connection, *, series_id: str) -> None:
        conn.execute("DELETE FROM overlay_instruction_versions WHERE series_id = ?", (series_id,))
        conn.execute("DELETE FROM overlay_series_state WHERE series_id = ?", (series_id,))

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT head_time FROM overlay_series_state WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return int(row["head_time"])

    def last_version_id(self, series_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(version_id) AS v FROM overlay_instruction_versions WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None or row["v"] is None:
                return 0
            return int(row["v"])

    def insert_instruction_version_in_conn(
        self,
        conn: sqlite3.Connection,
        *,
        series_id: str,
        instruction_id: str,
        kind: str,
        visible_time: int,
        payload: dict[str, Any],
    ) -> int:
        now_ms = int(time.time() * 1000)
        cur = conn.execute(
            """
            INSERT INTO overlay_instruction_versions(series_id, instruction_id, kind, visible_time, def_json, created_at_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                instruction_id,
                str(kind),
                int(visible_time),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                now_ms,
            ),
        )
        rowid = cur.lastrowid
        if rowid is None:
            raise RuntimeError("overlay_instruction_versions_insert_missing_rowid")
        return int(rowid)

    def get_latest_defs_up_to_time(
        self,
        *,
        series_id: str,
        up_to_time: int,
    ) -> list[OverlayInstructionVersionRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT v.version_id, v.series_id, v.instruction_id, v.kind, v.visible_time, v.def_json
                FROM overlay_instruction_versions v
                JOIN (
                  SELECT instruction_id, MAX(version_id) AS max_id
                  FROM overlay_instruction_versions
                  WHERE series_id = ? AND visible_time <= ?
                  GROUP BY instruction_id
                ) m
                ON v.instruction_id = m.instruction_id AND v.version_id = m.max_id
                WHERE v.series_id = ?
                """,
                (series_id, int(up_to_time), series_id),
            ).fetchall()
        out: list[OverlayInstructionVersionRow] = []
        for r in rows:
            payload: Any = {}
            try:
                payload = json.loads(r["def_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayInstructionVersionRow(
                    version_id=int(r["version_id"]),
                    series_id=str(r["series_id"]),
                    instruction_id=str(r["instruction_id"]),
                    kind=str(r["kind"]),
                    visible_time=int(r["visible_time"]),
                    payload=payload,
                )
            )
        return out

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
                """
                SELECT version_id, series_id, instruction_id, kind, visible_time, def_json
                FROM overlay_instruction_versions
                WHERE series_id = ? AND version_id > ? AND visible_time <= ?
                ORDER BY version_id ASC
                LIMIT ?
                """,
                (series_id, int(after_version_id), int(up_to_time), int(limit)),
            ).fetchall()
        out: list[OverlayInstructionVersionRow] = []
        for r in rows:
            payload: Any = {}
            try:
                payload = json.loads(r["def_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayInstructionVersionRow(
                    version_id=int(r["version_id"]),
                    series_id=str(r["series_id"]),
                    instruction_id=str(r["instruction_id"]),
                    kind=str(r["kind"]),
                    visible_time=int(r["visible_time"]),
                    payload=payload,
                )
            )
        return out

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
                """
                SELECT version_id, series_id, instruction_id, kind, visible_time, def_json
                FROM overlay_instruction_versions
                WHERE series_id = ? AND visible_time >= ? AND visible_time <= ?
                ORDER BY visible_time ASC, version_id ASC
                LIMIT ?
                """,
                (series_id, int(start_visible_time), int(end_visible_time), int(limit)),
            ).fetchall()
        out: list[OverlayInstructionVersionRow] = []
        for r in rows:
            payload: Any = {}
            try:
                payload = json.loads(r["def_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayInstructionVersionRow(
                    version_id=int(r["version_id"]),
                    series_id=str(r["series_id"]),
                    instruction_id=str(r["instruction_id"]),
                    kind=str(r["kind"]),
                    visible_time=int(r["visible_time"]),
                    payload=payload,
                )
            )
        return out

    def get_latest_def_for_instruction(
        self,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self.get_latest_def_for_instruction_in_conn(conn, series_id=series_id, instruction_id=instruction_id)

    def get_latest_def_for_instruction_in_conn(
        self,
        conn: sqlite3.Connection,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT def_json
            FROM overlay_instruction_versions
            WHERE series_id = ? AND instruction_id = ?
            ORDER BY version_id DESC
            LIMIT 1
            """,
            (series_id, instruction_id),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["def_json"])
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
