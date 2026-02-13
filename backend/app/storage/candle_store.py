from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .local_store_runtime import LocalConnectionBase, MemoryCursor
from ..core.schemas import CandleClosed


@dataclass
class _CandleStoreState:
    candles_by_series: dict[str, dict[int, CandleClosed]] = field(default_factory=dict)


_STORE_STATES: dict[str, _CandleStoreState] = {}
_STORE_STATES_LOCK = threading.Lock()


def _store_key(db_path: Path) -> str:
    return str(Path(db_path))


def _get_store_state(db_path: Path) -> _CandleStoreState:
    key = _store_key(db_path)
    with _STORE_STATES_LOCK:
        state = _STORE_STATES.get(key)
        if state is None:
            state = _CandleStoreState()
            _STORE_STATES[key] = state
        return state


class _CandleStoreConnection(LocalConnectionBase):
    def __init__(self, state: _CandleStoreState) -> None:
        super().__init__()
        self._state = state

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> MemoryCursor:
        normalized = " ".join(str(sql).strip().split()).lower()
        values = tuple(params)

        if normalized.startswith("select count(*) as n from candles where series_id = ?"):
            series_id = str(values[0]) if values else ""
            count = len(self._state.candles_by_series.get(series_id, {}))
            return MemoryCursor(rows=[self.build_row({"n": int(count)})], rowcount=1)

        if normalized.startswith("select count(1) as n from candles where series_id = ?"):
            series_id = str(values[0]) if values else ""
            count = len(self._state.candles_by_series.get(series_id, {}))
            return MemoryCursor(rows=[self.build_row({"n": int(count)})], rowcount=1)

        if normalized.startswith("select count(1) as c from candles where series_id = ?"):
            series_id = str(values[0]) if values else ""
            count = len(self._state.candles_by_series.get(series_id, {}))
            return MemoryCursor(rows=[self.build_row({"c": int(count)})], rowcount=1)

        raise RuntimeError(f"unsupported_local_store_sql:{sql.strip()[:96]}")


@dataclass(frozen=True)
class CandleStore:
    db_path: Path

    def connect(self) -> _CandleStoreConnection:
        return _CandleStoreConnection(_get_store_state(self.db_path))

    def _series_rows(self, *, state: _CandleStoreState, series_id: str) -> dict[int, CandleClosed]:
        rows = state.candles_by_series.get(series_id)
        if rows is None:
            rows = {}
            state.candles_by_series[series_id] = rows
        return rows

    def upsert_closed_in_conn(self, conn: _CandleStoreConnection, series_id: str, candle: CandleClosed) -> None:
        rows = self._series_rows(state=conn._state, series_id=series_id)
        rows[int(candle.candle_time)] = CandleClosed(
            candle_time=int(candle.candle_time),
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=float(candle.volume),
        )
        conn.total_changes += 1

    def upsert_many_closed_in_conn(self, conn: _CandleStoreConnection, series_id: str, candles: list[CandleClosed]) -> None:
        for candle in candles:
            self.upsert_closed_in_conn(conn, series_id, candle)

    def existing_closed_times_in_conn(
        self,
        conn: _CandleStoreConnection,
        *,
        series_id: str,
        candle_times: list[int],
    ) -> set[int]:
        rows = conn._state.candles_by_series.get(series_id, {})
        return {int(t) for t in candle_times if int(t) > 0 and int(t) in rows}

    def delete_closed_times_in_conn(self, conn: _CandleStoreConnection, *, series_id: str, candle_times: list[int]) -> int:
        rows = conn._state.candles_by_series.get(series_id, {})
        deleted = 0
        for candle_time in {int(t) for t in candle_times if int(t) > 0}:
            if candle_time in rows:
                rows.pop(candle_time, None)
                deleted += 1
        if deleted > 0:
            conn.total_changes += int(deleted)
        return int(deleted)

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:
        with self.connect() as conn:
            self.upsert_closed_in_conn(conn, series_id, candle)
            conn.commit()

    def head_time(self, series_id: str) -> int | None:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        if not rows:
            return None
        return int(max(rows))

    def first_time(self, series_id: str) -> int | None:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        if not rows:
            return None
        return int(min(rows))

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        start = int(start_time)
        end = int(end_time)
        return int(sum(1 for t in rows if start <= int(t) <= end))

    def trim_series_to_latest_n_in_conn(self, conn: _CandleStoreConnection, *, series_id: str, keep: int) -> int:
        keep_n = max(1, int(keep))
        rows = conn._state.candles_by_series.get(series_id, {})
        if len(rows) <= keep_n:
            return 0
        times_desc = sorted(rows.keys(), reverse=True)
        cutoff = int(times_desc[keep_n - 1])
        to_delete = [t for t in rows if int(t) < cutoff]
        for candle_time in to_delete:
            rows.pop(candle_time, None)
        deleted = len(to_delete)
        if deleted > 0:
            conn.total_changes += int(deleted)
        return int(deleted)

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        target = int(at_time)
        candidates = [int(t) for t in rows if int(t) <= target]
        if not candidates:
            return None
        return int(max(candidates))

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        ordered_times = sorted(int(t) for t in rows)
        if since is None:
            times = ordered_times[-int(limit) :] if int(limit) > 0 else []
        else:
            times = [t for t in ordered_times if int(t) > int(since)]
            times = times[: int(limit)] if int(limit) > 0 else []
        return [rows[t] for t in times]

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        rows = _get_store_state(self.db_path).candles_by_series.get(series_id, {})
        start = int(start_time)
        end = int(end_time)
        ordered_times = [t for t in sorted(int(v) for v in rows) if start <= int(t) <= end]
        if int(limit) > 0:
            ordered_times = ordered_times[: int(limit)]
        return [rows[t] for t in ordered_times]
