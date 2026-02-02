from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LatestLedgerRow:
    candle_id: str
    candle_time: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class OverlayEventRow:
    candle_id: str
    candle_time: int
    kind: str
    payload: dict[str, Any]
    id: int | None = None


@dataclass(frozen=True)
class PlotPointRow:
    feature_key: str
    candle_time: int
    value: float


class SqliteStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candles (
              candle_id TEXT PRIMARY KEY,
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              open_time INTEGER NOT NULL,
              open REAL NOT NULL,
              high REAL NOT NULL,
              low REAL NOT NULL,
              close REAL NOT NULL,
              volume REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kernel_state (
              key TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL
            );

            -- latest materialized ledger row (per symbol+timeframe)
            CREATE TABLE IF NOT EXISTS ledger_latest (
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              candle_id TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              PRIMARY KEY (symbol, timeframe)
            );

            CREATE TABLE IF NOT EXISTS overlay_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              candle_id TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              kind TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_overlay_events_series_time
              ON overlay_events(symbol, timeframe, candle_time);

            CREATE INDEX IF NOT EXISTS idx_overlay_events_series_id
              ON overlay_events(symbol, timeframe, id);

            -- plot points (time series) for chart overlays (e.g. indicators)
            CREATE TABLE IF NOT EXISTS plot_points (
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              feature_key TEXT NOT NULL,
              candle_id TEXT NOT NULL,
              candle_time INTEGER NOT NULL,
              value REAL NOT NULL,
              PRIMARY KEY (symbol, timeframe, feature_key, candle_time)
            );

            CREATE INDEX IF NOT EXISTS idx_plot_points_series_feature_time
              ON plot_points(symbol, timeframe, feature_key, candle_time);
            """
        )
        conn.commit()

    # --- candles ---
    def upsert_candle(self, conn: sqlite3.Connection, *, candle: Any) -> None:
        conn.execute(
            """
            INSERT INTO candles (candle_id, symbol, timeframe, open_time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candle_id) DO UPDATE SET
              open=excluded.open,
              high=excluded.high,
              low=excluded.low,
              close=excluded.close,
              volume=excluded.volume
            """,
            (
                candle.candle_id,
                candle.symbol,
                candle.timeframe,
                candle.open_time,
                float(candle.open),
                float(candle.high),
                float(candle.low),
                float(candle.close),
                float(candle.volume),
            ),
        )

    def get_latest_candle_id(self, conn: sqlite3.Connection, *, symbol: str, timeframe: str) -> str | None:
        row = conn.execute(
            """
            SELECT candle_id
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY open_time DESC
            LIMIT 1
            """,
            (symbol, timeframe),
        ).fetchone()
        return None if row is None else str(row["candle_id"])

    def get_latest_candle_time(self, conn: sqlite3.Connection, *, symbol: str, timeframe: str) -> int | None:
        row = conn.execute(
            """
            SELECT MAX(open_time) AS open_time
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        ).fetchone()
        if row is None or row["open_time"] is None:
            return None
        return int(row["open_time"])

    # --- kernel state ---
    def load_state(self, conn: sqlite3.Connection, *, key: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT payload_json FROM kernel_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row["payload_json"])

    def save_state(self, conn: sqlite3.Connection, *, key: str, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO kernel_state (key, payload_json) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (key, json.dumps(payload, separators=(",", ":"), sort_keys=True)),
        )

    # --- ledger / overlay ---
    def set_latest_ledger(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        candle_id: str,
        candle_time: int,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO ledger_latest (symbol, timeframe, candle_id, candle_time, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
              candle_id=excluded.candle_id,
              candle_time=excluded.candle_time,
              payload_json=excluded.payload_json
            """,
            (
                symbol,
                timeframe,
                candle_id,
                int(candle_time),
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
            ),
        )

    def get_latest_ledger(self, conn: sqlite3.Connection, *, symbol: str, timeframe: str) -> LatestLedgerRow | None:
        row = conn.execute(
            """
            SELECT candle_id, candle_time, payload_json
            FROM ledger_latest
            WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        ).fetchone()
        if row is None:
            return None
        return LatestLedgerRow(
            candle_id=str(row["candle_id"]),
            candle_time=int(row["candle_time"]),
            payload=json.loads(row["payload_json"]),
        )

    def append_overlay_event(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        candle_id: str,
        candle_time: int,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO overlay_events (symbol, timeframe, candle_id, candle_time, kind, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                timeframe,
                candle_id,
                int(candle_time),
                kind,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
            ),
        )

    def get_latest_overlay_event(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        kind: str,
    ) -> OverlayEventRow | None:
        row = conn.execute(
            """
            SELECT id, candle_id, candle_time, kind, payload_json
            FROM overlay_events
            WHERE symbol = ? AND timeframe = ? AND kind = ?
            ORDER BY candle_time DESC, id DESC
            LIMIT 1
            """,
            (symbol, timeframe, kind),
        ).fetchone()
        if row is None:
            return None
        return OverlayEventRow(
            candle_id=str(row["candle_id"]),
            candle_time=int(row["candle_time"]),
            kind=str(row["kind"]),
            payload=json.loads(row["payload_json"]),
            id=int(row["id"]),
        )

    def get_latest_overlay_event_id(self, conn: sqlite3.Connection, *, symbol: str, timeframe: str) -> int | None:
        row = conn.execute(
            """
            SELECT MAX(id) AS id
            FROM overlay_events
            WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        ).fetchone()
        if row is None or row["id"] is None:
            return None
        return int(row["id"])

    def get_overlay_events_since_id(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        since_id: int | None,
        limit: int = 5000,
    ) -> list[OverlayEventRow]:
        since_id = 0 if since_id is None else int(since_id)
        rows = conn.execute(
            """
            SELECT id, candle_id, candle_time, kind, payload_json
            FROM overlay_events
            WHERE symbol = ? AND timeframe = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (symbol, timeframe, since_id, int(limit)),
        ).fetchall()
        return [
            OverlayEventRow(
                candle_id=str(r["candle_id"]),
                candle_time=int(r["candle_time"]),
                kind=str(r["kind"]),
                payload=json.loads(r["payload_json"]),
                id=int(r["id"]),
            )
            for r in rows
        ]

    # --- plot points ---
    def upsert_plot_point(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        feature_key: str,
        candle_id: str,
        candle_time: int,
        value: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO plot_points (symbol, timeframe, feature_key, candle_id, candle_time, value)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, feature_key, candle_time) DO UPDATE SET
              candle_id=excluded.candle_id,
              value=excluded.value
            """,
            (symbol, timeframe, feature_key, candle_id, int(candle_time), float(value)),
        )

    def get_plot_points_since_time(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        feature_keys: list[str],
        since_time: int | None,
        limit: int = 5000,
    ) -> list[PlotPointRow]:
        if not feature_keys:
            return []

        since_time = -1 if since_time is None else int(since_time)
        placeholders = ",".join("?" for _ in feature_keys)
        rows = conn.execute(
            f"""
            SELECT feature_key, candle_time, value
            FROM plot_points
            WHERE symbol = ? AND timeframe = ? AND feature_key IN ({placeholders}) AND candle_time > ?
            ORDER BY candle_time ASC
            LIMIT ?
            """,
            (symbol, timeframe, *feature_keys, since_time, int(limit)),
        ).fetchall()
        return [
            PlotPointRow(feature_key=str(r["feature_key"]), candle_time=int(r["candle_time"]), value=float(r["value"]))
            for r in rows
        ]
