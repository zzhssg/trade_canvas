from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..local_store_runtime import LocalConnectionBase, MemoryCursor
from .store_local_sql import execute_local_factor_sql


@dataclass(frozen=True)
class FactorEventRow:
    id: int
    series_id: str
    factor_name: str
    candle_time: int
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


@dataclass
class _FactorStoreState:
    events: list[FactorEventRow] = field(default_factory=list)
    head_snapshots: list[FactorHeadSnapshotRow] = field(default_factory=list)
    series_head: dict[str, int] = field(default_factory=dict)
    fingerprints: dict[str, FactorSeriesFingerprintRow] = field(default_factory=dict)
    event_unique_keys: set[tuple[str, str, str]] = field(default_factory=set)
    next_event_id: int = 1
    next_head_snapshot_id: int = 1


_STORE_STATES: dict[str, _FactorStoreState] = {}
_STORE_STATES_LOCK = threading.Lock()


def _store_key(db_path: Path) -> str:
    return str(Path(db_path))


def _get_store_state(db_path: Path) -> _FactorStoreState:
    key = _store_key(db_path)
    with _STORE_STATES_LOCK:
        state = _STORE_STATES.get(key)
        if state is None:
            state = _FactorStoreState()
            _STORE_STATES[key] = state
        return state


class _FactorStoreConnection(LocalConnectionBase):
    def __init__(self, state: _FactorStoreState) -> None:
        super().__init__()
        self._state = state

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> MemoryCursor:
        return execute_local_factor_sql(
            conn=self,
            state=self._state,
            sql=sql,
            params=params,
        )


@dataclass(frozen=True)
class FactorStore:
    db_path: Path

    def connect(self) -> _FactorStoreConnection:
        return _FactorStoreConnection(_get_store_state(self.db_path))

    def upsert_head_time_in_conn(self, conn: _FactorStoreConnection, *, series_id: str, head_time: int) -> None:
        sid = str(series_id)
        next_head = int(head_time)
        current = conn._state.series_head.get(sid)
        merged = max(int(current), next_head) if current is not None else next_head
        conn._state.series_head[sid] = int(merged)
        conn.total_changes += 1

    def head_time(self, series_id: str) -> int | None:
        value = _get_store_state(self.db_path).series_head.get(str(series_id))
        return None if value is None else int(value)

    def get_series_fingerprint(self, series_id: str) -> FactorSeriesFingerprintRow | None:
        row = _get_store_state(self.db_path).fingerprints.get(str(series_id))
        if row is None:
            return None
        return FactorSeriesFingerprintRow(
            series_id=str(row.series_id),
            fingerprint=str(row.fingerprint),
            updated_at_ms=int(row.updated_at_ms),
        )

    def upsert_series_fingerprint_in_conn(self, conn: _FactorStoreConnection, *, series_id: str, fingerprint: str) -> None:
        sid = str(series_id)
        conn._state.fingerprints[sid] = FactorSeriesFingerprintRow(
            series_id=sid,
            fingerprint=str(fingerprint),
            updated_at_ms=int(time.time() * 1000),
        )
        conn.total_changes += 1

    def clear_series_in_conn(self, conn: _FactorStoreConnection, *, series_id: str) -> None:
        sid = str(series_id)
        before_events = len(conn._state.events)
        before_heads = len(conn._state.head_snapshots)
        conn._state.events = [row for row in conn._state.events if str(row.series_id) != sid]
        conn._state.head_snapshots = [row for row in conn._state.head_snapshots if str(row.series_id) != sid]
        conn._state.series_head.pop(sid, None)
        conn._state.event_unique_keys = {
            key for key in conn._state.event_unique_keys if str(key[0]) != sid
        }
        deleted = (before_events - len(conn._state.events)) + (before_heads - len(conn._state.head_snapshots))
        if deleted > 0:
            conn.total_changes += int(deleted)

    def last_event_id(self, series_id: str) -> int:
        sid = str(series_id)
        event_ids = [int(row.id) for row in _get_store_state(self.db_path).events if str(row.series_id) == sid]
        return int(max(event_ids)) if event_ids else 0

    def insert_events_in_conn(self, conn: _FactorStoreConnection, *, events: list[FactorEventWrite]) -> None:
        inserted = 0
        for event in events:
            key = (str(event.series_id), str(event.factor_name), str(event.event_key))
            if key in conn._state.event_unique_keys:
                continue
            conn._state.event_unique_keys.add(key)
            conn._state.events.append(
                FactorEventRow(
                    id=int(conn._state.next_event_id),
                    series_id=str(event.series_id),
                    factor_name=str(event.factor_name),
                    candle_time=int(event.candle_time),
                    kind=str(event.kind),
                    event_key=str(event.event_key),
                    payload=dict(event.payload or {}),
                )
            )
            conn._state.next_event_id += 1
            inserted += 1
        if inserted > 0:
            conn.total_changes += int(inserted)

    def insert_head_snapshot_in_conn(
        self,
        conn: _FactorStoreConnection,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
        head: dict[str, Any],
    ) -> int | None:
        sid = str(series_id)
        fname = str(factor_name)
        ctime = int(candle_time)
        rows = [
            row
            for row in conn._state.head_snapshots
            if str(row.series_id) == sid and str(row.factor_name) == fname and int(row.candle_time) == ctime
        ]
        rows.sort(key=lambda row: int(row.seq), reverse=True)
        if rows:
            latest = rows[0]
            if dict(latest.head or {}) == dict(head or {}):
                return int(latest.seq)
            next_seq = int(latest.seq) + 1
        else:
            next_seq = 0

        conn._state.head_snapshots.append(
            FactorHeadSnapshotRow(
                id=int(conn._state.next_head_snapshot_id),
                series_id=sid,
                factor_name=fname,
                candle_time=ctime,
                seq=int(next_seq),
                head=dict(head or {}),
            )
        )
        conn._state.next_head_snapshot_id += 1
        conn.total_changes += 1
        return int(next_seq)

    def get_head_at_or_before(
        self,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
    ) -> FactorHeadSnapshotRow | None:
        sid = str(series_id)
        fname = str(factor_name)
        ctime = int(candle_time)
        candidates = [
            row
            for row in _get_store_state(self.db_path).head_snapshots
            if str(row.series_id) == sid and str(row.factor_name) == fname and int(row.candle_time) <= ctime
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: (int(row.candle_time), int(row.seq)), reverse=True)
        return candidates[0]

    def get_events_between_times(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list[FactorEventRow]:
        sid = str(series_id)
        start_time = int(start_candle_time)
        end_time = int(end_candle_time)
        fname = None if factor_name is None else str(factor_name)
        rows = [
            row
            for row in _get_store_state(self.db_path).events
            if str(row.series_id) == sid
            and start_time <= int(row.candle_time) <= end_time
            and (fname is None or str(row.factor_name) == fname)
        ]
        rows.sort(key=lambda row: (int(row.candle_time), int(row.id)))
        if int(limit) > 0:
            rows = rows[: int(limit)]
        return list(rows)

    def get_events_between_times_paged(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        page_size: int = 20000,
    ) -> list[FactorEventRow]:
        page = max(1, int(page_size))
        rows = self.get_events_between_times(
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=int(start_candle_time),
            end_candle_time=int(end_candle_time),
            limit=10**9,
        )
        out: list[FactorEventRow] = []
        for idx in range(0, len(rows), page):
            out.extend(rows[idx : idx + page])
        return out

    def iter_events_between_times_paged(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        page_size: int = 20000,
    ) -> Iterator[FactorEventRow]:
        for row in self.get_events_between_times_paged(
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=int(start_candle_time),
            end_candle_time=int(end_candle_time),
            page_size=int(page_size),
        ):
            yield row
