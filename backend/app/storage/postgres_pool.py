from __future__ import annotations

import importlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

from .contracts import DbConnection

class _PostgresDriver(Protocol):
    def connect(self, dsn: str, *, connect_timeout: int) -> DbConnection: ...


@dataclass(frozen=True)
class PostgresPoolSettings:
    dsn: str
    connect_timeout_s: float = 5.0
    min_size: int = 1
    max_size: int = 10


def _load_postgres_driver() -> _PostgresDriver | None:
    try:
        module = importlib.import_module("psycopg")
    except ImportError:
        return None
    return module if hasattr(module, "connect") else None


class PostgresPool:
    """
    Minimal Postgres connection provider for bootstrap/management tasks.

    M1 keeps runtime read/write path on SQLite; this pool is only used for
    fail-fast schema bootstrap under feature flag.
    """

    def __init__(self, settings: PostgresPoolSettings) -> None:
        self._settings = PostgresPoolSettings(
            dsn=str(settings.dsn or "").strip(),
            connect_timeout_s=max(0.1, float(settings.connect_timeout_s)),
            min_size=max(1, int(settings.min_size)),
            max_size=max(max(1, int(settings.min_size)), int(settings.max_size)),
        )

    @property
    def settings(self) -> PostgresPoolSettings:
        return self._settings

    @staticmethod
    def driver_available() -> bool:
        return _load_postgres_driver() is not None

    @contextmanager
    def connect(self) -> Iterator[DbConnection]:
        driver = _load_postgres_driver()
        if driver is None:
            raise RuntimeError("postgres_driver_missing:install_psycopg")
        conn = driver.connect(
            self._settings.dsn,
            connect_timeout=max(1, int(self._settings.connect_timeout_s)),
        )
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass
