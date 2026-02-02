from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlotLinePointRow:
    series_id: str
    feature_key: str
    candle_time: int
    value: float


@dataclass(frozen=True)
class OverlayEventRow:
    id: int
    series_id: str
    candle_time: int
    kind: str
    candle_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class OverlayEventWrite:
    series_id: str
    candle_time: int
    kind: str
    candle_id: str
    pivot_time: int | None
    direction: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class PlotStore:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_series_state (
              series_id TEXT PRIMARY KEY,
              head_time INTEGER NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_line_points (
              series_id TEXT NOT NULL,
              feature_key TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              value REAL NOT NULL,
              PRIMARY KEY (series_id, feature_key, candle_time)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plot_line_points_series_time ON plot_line_points(series_id, candle_time);"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_overlay_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              series_id TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              kind TEXT NOT NULL,
              candle_id TEXT NOT NULL,
              pivot_time INTEGER,
              direction TEXT,
              payload_json TEXT NOT NULL,
              created_at_ms INTEGER NOT NULL,
              UNIQUE (series_id, kind, pivot_time, direction)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plot_events_series_id ON plot_overlay_events(series_id, id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plot_events_series_time ON plot_overlay_events(series_id, candle_time);"
        )

        conn.commit()

    def upsert_head_time_in_conn(self, conn: sqlite3.Connection, *, series_id: str, head_time: int) -> None:
        conn.execute(
            """
            INSERT INTO plot_series_state(series_id, head_time, updated_at_ms)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
              head_time=excluded.head_time,
              updated_at_ms=excluded.updated_at_ms
            """,
            (series_id, int(head_time), int(time.time() * 1000)),
        )

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT head_time FROM plot_series_state WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return int(row["head_time"])

    def insert_overlay_events_in_conn(self, conn: sqlite3.Connection, *, events: list[OverlayEventWrite]) -> None:
        if not events:
            return
        now_ms = int(time.time() * 1000)
        conn.executemany(
            """
            INSERT INTO plot_overlay_events(
              series_id, candle_time, kind, candle_id, pivot_time, direction, payload_json, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, kind, pivot_time, direction) DO NOTHING
            """,
            [
                (
                    e.series_id,
                    int(e.candle_time),
                    str(e.kind),
                    str(e.candle_id),
                    int(e.pivot_time) if e.pivot_time is not None else None,
                    str(e.direction) if e.direction is not None else None,
                    json.dumps(e.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    now_ms,
                )
                for e in events
            ],
        )

    def get_overlay_events_after_id(
        self, *, series_id: str, after_id: int, limit: int = 5000
    ) -> list[OverlayEventRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, series_id, candle_time, kind, candle_id, payload_json
                FROM plot_overlay_events
                WHERE series_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (series_id, int(after_id), int(limit)),
            ).fetchall()
        out: list[OverlayEventRow] = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["payload_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayEventRow(
                    id=int(r["id"]),
                    series_id=str(r["series_id"]),
                    candle_time=int(r["candle_time"]),
                    kind=str(r["kind"]),
                    candle_id=str(r["candle_id"]),
                    payload=payload,
                )
            )
        return out

    def get_overlay_events_since_candle_time(
        self, *, series_id: str, since_candle_time: int, limit: int = 20000
    ) -> list[OverlayEventRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, series_id, candle_time, kind, candle_id, payload_json
                FROM plot_overlay_events
                WHERE series_id = ? AND candle_time >= ?
                ORDER BY candle_time ASC, id ASC
                LIMIT ?
                """,
                (series_id, int(since_candle_time), int(limit)),
            ).fetchall()
        out: list[OverlayEventRow] = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["payload_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayEventRow(
                    id=int(r["id"]),
                    series_id=str(r["series_id"]),
                    candle_time=int(r["candle_time"]),
                    kind=str(r["kind"]),
                    candle_id=str(r["candle_id"]),
                    payload=payload,
                )
            )
        return out

    def get_overlay_events_between_times(
        self,
        *,
        series_id: str,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list[OverlayEventRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, series_id, candle_time, kind, candle_id, payload_json
                FROM plot_overlay_events
                WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
                ORDER BY candle_time ASC, id ASC
                LIMIT ?
                """,
                (series_id, int(start_candle_time), int(end_candle_time), int(limit)),
            ).fetchall()
        out: list[OverlayEventRow] = []
        for r in rows:
            payload = {}
            try:
                payload = json.loads(r["payload_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                OverlayEventRow(
                    id=int(r["id"]),
                    series_id=str(r["series_id"]),
                    candle_time=int(r["candle_time"]),
                    kind=str(r["kind"]),
                    candle_id=str(r["candle_id"]),
                    payload=payload,
                )
            )
        return out
