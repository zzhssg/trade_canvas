from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .flags import resolve_env_float


_init_lock = threading.Lock()
_wal_inited: set[str] = set()


def _sqlite_timeout_s() -> float:
    return resolve_env_float("TRADE_CANVAS_SQLITE_TIMEOUT_S", fallback=5.0, minimum=0.1)


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
