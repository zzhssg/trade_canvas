from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal, Self, TypeVar

StateT = TypeVar("StateT")


def store_key(db_path: Path) -> str:
    return str(Path(db_path))


def get_or_create_store_state(
    *,
    store_states: dict[str, StateT],
    lock: Lock,
    db_path: Path,
    factory: Callable[[], StateT],
) -> StateT:
    key = store_key(db_path)
    with lock:
        state = store_states.get(key)
        if state is None:
            state = factory()
            store_states[key] = state
        return state


def merge_series_head_time(*, series_head: dict[str, int], series_id: str, head_time: int) -> int:
    sid = str(series_id)
    next_head = int(head_time)
    current = series_head.get(sid)
    merged = max(int(current), next_head) if current is not None else next_head
    series_head[sid] = int(merged)
    return int(merged)


def read_series_head_time(*, series_head: dict[str, int], series_id: str) -> int | None:
    value = series_head.get(str(series_id))
    return None if value is None else int(value)


@dataclass(frozen=True)
class MemoryRow:
    _data: dict[str, Any]
    _order: tuple[str, ...]

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            if key < 0 or key >= len(self._order):
                raise IndexError(key)
            return self._data[self._order[key]]
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self) -> tuple[str, ...]:
        return self._order


class MemoryCursor:
    def __init__(
        self,
        *,
        rows: list[MemoryRow] | None = None,
        rowcount: int = 0,
        lastrowid: int | None = None,
    ) -> None:
        self._rows = list(rows or [])
        self.rowcount = int(rowcount)
        self.lastrowid = lastrowid

    def fetchone(self) -> MemoryRow | None:
        if not self._rows:
            return None
        return self._rows[0]

    def fetchall(self) -> list[MemoryRow]:
        return list(self._rows)


class LocalConnectionBase:
    def __init__(self) -> None:
        self.total_changes = 0
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        return False

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self._closed = True

    def executemany(self, sql: str, seq_of_params: list[tuple[Any, ...]]) -> MemoryCursor:
        total = 0
        last_rowid: int | None = None
        for params in seq_of_params:
            cur = self.execute(sql, params)
            total += int(getattr(cur, "rowcount", 0) or 0)
            raw_lastrowid = getattr(cur, "lastrowid", None)
            if raw_lastrowid is not None:
                last_rowid = int(raw_lastrowid)
        return MemoryCursor(rowcount=total, lastrowid=last_rowid)

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> MemoryCursor:
        raise RuntimeError(f"unsupported_local_store_sql:{sql.strip()[:64]}")

    @staticmethod
    def build_row(data: dict[str, Any], *, order: tuple[str, ...] | None = None) -> MemoryRow:
        keys = order if order is not None else tuple(data.keys())
        return MemoryRow(_data=dict(data), _order=keys)
