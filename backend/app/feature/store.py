from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..storage.local_store_runtime import (
    LocalConnectionBase,
    get_or_create_store_state,
    merge_series_head_time,
    read_series_head_time,
)
from .contracts import FeatureValue


@dataclass(frozen=True)
class FeatureVectorRow:
    id: int
    series_id: str
    candle_time: int
    candle_id: str
    values: dict[str, FeatureValue]


@dataclass(frozen=True)
class FeatureVectorWrite:
    series_id: str
    candle_time: int
    candle_id: str
    values: dict[str, FeatureValue]


@dataclass
class _FeatureStoreState:
    rows: list[FeatureVectorRow] = field(default_factory=list)
    series_head: dict[str, int] = field(default_factory=dict)
    row_index: dict[tuple[str, int], int] = field(default_factory=dict)
    next_row_id: int = 1


_STORE_STATES: dict[str, _FeatureStoreState] = {}
_STORE_STATES_LOCK = threading.Lock()


def _get_store_state(db_path: Path) -> _FeatureStoreState:
    return get_or_create_store_state(
        store_states=_STORE_STATES,
        lock=_STORE_STATES_LOCK,
        db_path=db_path,
        factory=_FeatureStoreState,
    )


class _FeatureStoreConnection(LocalConnectionBase):
    def __init__(self, state: _FeatureStoreState) -> None:
        super().__init__()
        self._state = state


@dataclass(frozen=True)
class FeatureStore:
    db_path: Path

    def connect(self) -> _FeatureStoreConnection:
        return _FeatureStoreConnection(_get_store_state(self.db_path))

    def upsert_head_time_in_conn(self, conn: _FeatureStoreConnection, *, series_id: str, head_time: int) -> None:
        merge_series_head_time(
            series_head=conn._state.series_head,
            series_id=series_id,
            head_time=head_time,
        )
        conn.total_changes += 1

    def head_time(self, series_id: str) -> int | None:
        return read_series_head_time(
            series_head=_get_store_state(self.db_path).series_head,
            series_id=series_id,
        )

    def clear_series_in_conn(self, conn: _FeatureStoreConnection, *, series_id: str) -> None:
        sid = str(series_id)
        before_count = len(conn._state.rows)
        conn._state.rows = [row for row in conn._state.rows if str(row.series_id) != sid]
        conn._state.series_head.pop(sid, None)
        conn._state.row_index = {
            (str(row.series_id), int(row.candle_time)): int(idx)
            for idx, row in enumerate(conn._state.rows)
        }
        deleted = before_count - len(conn._state.rows)
        if deleted > 0:
            conn.total_changes += int(deleted)

    def upsert_rows_in_conn(self, conn: _FeatureStoreConnection, *, rows: list[FeatureVectorWrite]) -> int:
        changed = 0
        for row in rows:
            sid = str(row.series_id)
            candle_time = int(row.candle_time)
            key = (sid, candle_time)
            values = dict(row.values or {})
            candle_id = str(row.candle_id)
            index = conn._state.row_index.get(key)
            if index is None:
                conn._state.rows.append(
                    FeatureVectorRow(
                        id=int(conn._state.next_row_id),
                        series_id=sid,
                        candle_time=candle_time,
                        candle_id=candle_id,
                        values=values,
                    )
                )
                conn._state.row_index[key] = len(conn._state.rows) - 1
                conn._state.next_row_id += 1
                changed += 1
                continue

            existing = conn._state.rows[index]
            if existing.candle_id == candle_id and dict(existing.values or {}) == values:
                continue
            conn._state.rows[index] = FeatureVectorRow(
                id=int(existing.id),
                series_id=sid,
                candle_time=candle_time,
                candle_id=candle_id,
                values=values,
            )
            changed += 1

        if changed > 0:
            conn.total_changes += int(changed)
        return int(changed)

    def get_rows_between_times(
        self,
        *,
        series_id: str,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list[FeatureVectorRow]:
        sid = str(series_id)
        start_time = int(start_candle_time)
        end_time = int(end_candle_time)
        rows = [
            row
            for row in _get_store_state(self.db_path).rows
            if str(row.series_id) == sid and start_time <= int(row.candle_time) <= end_time
        ]
        rows.sort(key=lambda row: (int(row.candle_time), int(row.id)))
        if int(limit) > 0:
            rows = rows[: int(limit)]
        return list(rows)

    def iter_rows_between_times_paged(
        self,
        *,
        series_id: str,
        start_candle_time: int,
        end_candle_time: int,
        page_size: int = 20000,
    ) -> Iterator[FeatureVectorRow]:
        page = max(1, int(page_size))
        rows = self.get_rows_between_times(
            series_id=series_id,
            start_candle_time=int(start_candle_time),
            end_candle_time=int(end_candle_time),
            limit=10**9,
        )
        for idx in range(0, len(rows), page):
            for row in rows[idx : idx + page]:
                yield row

    def get_row_at_or_before(self, *, series_id: str, candle_time: int) -> FeatureVectorRow | None:
        sid = str(series_id)
        ctime = int(candle_time)
        rows = [
            row
            for row in _get_store_state(self.db_path).rows
            if str(row.series_id) == sid and int(row.candle_time) <= ctime
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: (int(row.candle_time), int(row.id)), reverse=True)
        return rows[0]

