from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path


_init_lock = threading.Lock()
_wal_inited: set[str] = set()


def _sqlite_timeout_s() -> float:
    raw = (os.environ.get("TRADE_CANVAS_SQLITE_TIMEOUT_S") or "").strip()
    if not raw:
        return 5.0
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 5.0


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=_sqlite_timeout_s())
    conn.row_factory = sqlite3.Row

    # Per-connection pragmas.
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")

    # Database-level journaling mode: setting it repeatedly under concurrent load can cause lock contention.
    # Do it once per process per db_path.
    key = str(db_path)
    if key not in _wal_inited:
        with _init_lock:
            if key not in _wal_inited:
                conn.execute("PRAGMA journal_mode=WAL;")
                _wal_inited.add(key)

    return conn

