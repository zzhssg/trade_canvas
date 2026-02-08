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
class FactorEventRow:
    id: int
    series_id: str
    factor_name: str
    candle_time: int  # visible_time (unix seconds)
    kind: str
    event_key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class FactorEventWrite:
    series_id: str
    factor_name: str
    candle_time: int
    kind: str
    event_key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class FactorHeadSnapshotRow:
    id: int
    series_id: str
    factor_name: str
    candle_time: int
    seq: int
    head: dict[str, Any]


@dataclass(frozen=True)
class FactorSeriesFingerprintRow:
    series_id: str
    fingerprint: str
    updated_at_ms: int


@dataclass(frozen=True)
class FactorStore:
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
            CREATE TABLE IF NOT EXISTS factor_series_state (
              series_id TEXT PRIMARY KEY,
              head_time INTEGER NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              series_id TEXT NOT NULL,
              factor_name TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              kind TEXT NOT NULL,
              event_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at_ms INTEGER NOT NULL,
              UNIQUE (series_id, factor_name, event_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_head_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              series_id TEXT NOT NULL,
              factor_name TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              seq INTEGER NOT NULL,
              head_json TEXT NOT NULL,
              created_at_ms INTEGER NOT NULL,
              UNIQUE (series_id, factor_name, candle_time, seq)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_series_fingerprint (
              series_id TEXT PRIMARY KEY,
              fingerprint TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_factor_events_series_time ON factor_events(series_id, candle_time);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_factor_events_series_factor_time ON factor_events(series_id, factor_name, candle_time);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_factor_head_series_factor_time ON factor_head_snapshots(series_id, factor_name, candle_time);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_factor_head_series_time ON factor_head_snapshots(series_id, candle_time);")
        conn.commit()

    def upsert_head_time_in_conn(self, conn: sqlite3.Connection, *, series_id: str, head_time: int) -> None:
        conn.execute(
            """
            INSERT INTO factor_series_state(series_id, head_time, updated_at_ms)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
              head_time=MAX(head_time, excluded.head_time),
              updated_at_ms=excluded.updated_at_ms
            """,
            (series_id, int(head_time), int(time.time() * 1000)),
        )

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT head_time FROM factor_series_state WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return int(row["head_time"])

    def get_series_fingerprint(self, series_id: str) -> FactorSeriesFingerprintRow | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT series_id, fingerprint, updated_at_ms FROM factor_series_fingerprint WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None:
                return None
            return FactorSeriesFingerprintRow(
                series_id=str(row["series_id"]),
                fingerprint=str(row["fingerprint"]),
                updated_at_ms=int(row["updated_at_ms"]),
            )

    def upsert_series_fingerprint_in_conn(self, conn: sqlite3.Connection, *, series_id: str, fingerprint: str) -> None:
        conn.execute(
            """
            INSERT INTO factor_series_fingerprint(series_id, fingerprint, updated_at_ms)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
              fingerprint=excluded.fingerprint,
              updated_at_ms=excluded.updated_at_ms
            """,
            (series_id, str(fingerprint), int(time.time() * 1000)),
        )

    def clear_series_in_conn(self, conn: sqlite3.Connection, *, series_id: str) -> None:
        conn.execute("DELETE FROM factor_events WHERE series_id = ?", (series_id,))
        conn.execute("DELETE FROM factor_head_snapshots WHERE series_id = ?", (series_id,))
        conn.execute("DELETE FROM factor_series_state WHERE series_id = ?", (series_id,))

    def last_event_id(self, series_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(id) AS v FROM factor_events WHERE series_id = ?",
                (series_id,),
            ).fetchone()
            if row is None or row["v"] is None:
                return 0
            return int(row["v"])

    def insert_events_in_conn(self, conn: sqlite3.Connection, *, events: list[FactorEventWrite]) -> None:
        if not events:
            return
        now_ms = int(time.time() * 1000)
        conn.executemany(
            """
            INSERT INTO factor_events(
              series_id, factor_name, candle_time, kind, event_key, payload_json, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, factor_name, event_key) DO NOTHING
            """,
            [
                (
                    e.series_id,
                    e.factor_name,
                    int(e.candle_time),
                    str(e.kind),
                    str(e.event_key),
                    json.dumps(e.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    now_ms,
                )
                for e in events
            ],
        )

    def insert_head_snapshot_in_conn(
        self,
        conn: sqlite3.Connection,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
        head: dict[str, Any],
    ) -> int | None:
        if head is None:
            return None
        row = conn.execute(
            """
            SELECT seq, head_json
            FROM factor_head_snapshots
            WHERE series_id = ? AND factor_name = ? AND candle_time = ?
            ORDER BY seq DESC
            LIMIT 1
            """,
            (series_id, factor_name, int(candle_time)),
        ).fetchone()
        if row is not None:
            try:
                prev = json.loads(row["head_json"])
            except Exception:
                prev = None
            if isinstance(prev, dict) and prev == head:
                return int(row["seq"])
            next_seq = int(row["seq"]) + 1
        else:
            next_seq = 0

        now_ms = int(time.time() * 1000)
        conn.execute(
            """
            INSERT INTO factor_head_snapshots(
              series_id, factor_name, candle_time, seq, head_json, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                factor_name,
                int(candle_time),
                int(next_seq),
                json.dumps(head, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                now_ms,
            ),
        )
        return int(next_seq)

    def get_head_at_or_before(
        self,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
    ) -> FactorHeadSnapshotRow | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, series_id, factor_name, candle_time, seq, head_json
                FROM factor_head_snapshots
                WHERE series_id = ? AND factor_name = ? AND candle_time <= ?
                ORDER BY candle_time DESC, seq DESC
                LIMIT 1
                """,
                (series_id, factor_name, int(candle_time)),
            ).fetchone()
        if row is None:
            return None
        payload: Any = {}
        try:
            payload = json.loads(row["head_json"])
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return FactorHeadSnapshotRow(
            id=int(row["id"]),
            series_id=str(row["series_id"]),
            factor_name=str(row["factor_name"]),
            candle_time=int(row["candle_time"]),
            seq=int(row["seq"]),
            head=payload,
        )

    def get_events_between_times(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list[FactorEventRow]:
        with self.connect() as conn:
            if factor_name:
                rows = conn.execute(
                    """
                    SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                    FROM factor_events
                    WHERE series_id = ? AND factor_name = ? AND candle_time >= ? AND candle_time <= ?
                    ORDER BY candle_time ASC, id ASC
                    LIMIT ?
                    """,
                    (series_id, factor_name, int(start_candle_time), int(end_candle_time), int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                    FROM factor_events
                    WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
                    ORDER BY candle_time ASC, id ASC
                    LIMIT ?
                    """,
                    (series_id, int(start_candle_time), int(end_candle_time), int(limit)),
                ).fetchall()

        out: list[FactorEventRow] = []
        for r in rows:
            payload: Any = {}
            try:
                payload = json.loads(r["payload_json"])
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                FactorEventRow(
                    id=int(r["id"]),
                    series_id=str(r["series_id"]),
                    factor_name=str(r["factor_name"]),
                    candle_time=int(r["candle_time"]),
                    kind=str(r["kind"]),
                    event_key=str(r["event_key"]),
                    payload=payload,
                )
            )
        return out
