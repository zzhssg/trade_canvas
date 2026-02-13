from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .store import CandleStore
from .storage import PostgresPool


def _row_get(row: Any, *, index: int, key: str) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            pass
    return row[index]


def _safe_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class ReconcileSideSnapshot:
    head_time: int | None
    first_time: int | None
    count: int
    candle_time_sum: int
    close_micro_sum: int


@dataclass(frozen=True)
class ReconcileDiffSnapshot:
    head_match: bool
    count_match: bool
    checksum_match: bool
    match: bool


@dataclass(frozen=True)
class ReconcileSeriesSnapshot:
    series_id: str
    range_start: int | None
    range_end: int | None
    sqlite: ReconcileSideSnapshot
    postgres: ReconcileSideSnapshot
    diff: ReconcileDiffSnapshot

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DataReconcileService:
    def __init__(self, *, sqlite_store: CandleStore, pg_pool: PostgresPool | None, pg_schema: str) -> None:
        self._sqlite_store = sqlite_store
        schema = str(pg_schema or "").strip() or "public"
        self._pg_table = f"{schema}.candles"
        self._pg_pool = pg_pool

    def _require_pg_pool(self) -> PostgresPool:
        pool = self._pg_pool
        if pool is None:
            raise RuntimeError("postgres_pool_not_configured")
        return pool

    def _sqlite_head_time(self, *, series_id: str) -> int | None:
        return self._sqlite_store.head_time(series_id)

    def _sqlite_first_time(self, *, series_id: str) -> int | None:
        return self._sqlite_store.first_time(series_id)

    def _sqlite_stats(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
    ) -> tuple[int, int, int]:
        with self._sqlite_store.connect() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(1) AS cnt,
                  COALESCE(SUM(candle_time), 0) AS candle_time_sum,
                  COALESCE(SUM(CAST(ROUND(close * 1000000.0) AS INTEGER)), 0) AS close_micro_sum
                FROM candles
                WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
                """,
                (str(series_id), int(start_time), int(end_time)),
            ).fetchone()
        if row is None:
            return 0, 0, 0
        return (
            int(_safe_int(_row_get(row, index=0, key="cnt"), default=0) or 0),
            int(_safe_int(_row_get(row, index=1, key="candle_time_sum"), default=0) or 0),
            int(_safe_int(_row_get(row, index=2, key="close_micro_sum"), default=0) or 0),
        )

    def _postgres_head_time(self, *, series_id: str) -> int | None:
        with self._require_pg_pool().connect() as conn:
            row = conn.execute(
                f"SELECT MAX(candle_time) AS head_time FROM {self._pg_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        return _safe_int(_row_get(row, index=0, key="head_time"))

    def _postgres_first_time(self, *, series_id: str) -> int | None:
        with self._require_pg_pool().connect() as conn:
            row = conn.execute(
                f"SELECT MIN(candle_time) AS first_time FROM {self._pg_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        return _safe_int(_row_get(row, index=0, key="first_time"))

    def _postgres_stats(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
    ) -> tuple[int, int, int]:
        with self._require_pg_pool().connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                  COUNT(1) AS cnt,
                  COALESCE(SUM(candle_time), 0) AS candle_time_sum,
                  COALESCE(SUM(CAST(ROUND(close * 1000000.0) AS BIGINT)), 0) AS close_micro_sum
                FROM {self._pg_table}
                WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
                """,
                (str(series_id), int(start_time), int(end_time)),
            ).fetchone()
        if row is None:
            return 0, 0, 0
        return (
            int(_safe_int(_row_get(row, index=0, key="cnt"), default=0) or 0),
            int(_safe_int(_row_get(row, index=1, key="candle_time_sum"), default=0) or 0),
            int(_safe_int(_row_get(row, index=2, key="close_micro_sum"), default=0) or 0),
        )

    @staticmethod
    def _resolve_range(
        *,
        start_time: int | None,
        end_time: int | None,
        sqlite_first: int | None,
        sqlite_head: int | None,
        pg_first: int | None,
        pg_head: int | None,
    ) -> tuple[int | None, int | None]:
        left = int(start_time) if start_time is not None else None
        right = int(end_time) if end_time is not None else None
        if left is None:
            cands = [v for v in (sqlite_first, pg_first) if v is not None]
            left = int(min(cands)) if cands else None
        if right is None:
            cands = [v for v in (sqlite_head, pg_head) if v is not None]
            right = int(max(cands)) if cands else None
        if left is not None and right is not None and int(left) > int(right):
            raise ValueError("reconcile_range_invalid")
        return left, right

    def reconcile_series(
        self,
        *,
        series_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> ReconcileSeriesSnapshot:
        if self._pg_pool is None:
            raise RuntimeError("postgres_pool_not_configured")
        sid = str(series_id or "").strip()
        if not sid:
            raise ValueError("series_id_required")

        sqlite_head = self._sqlite_head_time(series_id=sid)
        sqlite_first = self._sqlite_first_time(series_id=sid)
        pg_head = self._postgres_head_time(series_id=sid)
        pg_first = self._postgres_first_time(series_id=sid)
        range_start, range_end = self._resolve_range(
            start_time=start_time,
            end_time=end_time,
            sqlite_first=sqlite_first,
            sqlite_head=sqlite_head,
            pg_first=pg_first,
            pg_head=pg_head,
        )

        if range_start is None or range_end is None:
            sqlite_side = ReconcileSideSnapshot(
                head_time=sqlite_head,
                first_time=sqlite_first,
                count=0,
                candle_time_sum=0,
                close_micro_sum=0,
            )
            pg_side = ReconcileSideSnapshot(
                head_time=pg_head,
                first_time=pg_first,
                count=0,
                candle_time_sum=0,
                close_micro_sum=0,
            )
        else:
            sqlite_count, sqlite_candle_time_sum, sqlite_close_micro_sum = self._sqlite_stats(
                series_id=sid,
                start_time=int(range_start),
                end_time=int(range_end),
            )
            pg_count, pg_candle_time_sum, pg_close_micro_sum = self._postgres_stats(
                series_id=sid,
                start_time=int(range_start),
                end_time=int(range_end),
            )
            sqlite_side = ReconcileSideSnapshot(
                head_time=sqlite_head,
                first_time=sqlite_first,
                count=int(sqlite_count),
                candle_time_sum=int(sqlite_candle_time_sum),
                close_micro_sum=int(sqlite_close_micro_sum),
            )
            pg_side = ReconcileSideSnapshot(
                head_time=pg_head,
                first_time=pg_first,
                count=int(pg_count),
                candle_time_sum=int(pg_candle_time_sum),
                close_micro_sum=int(pg_close_micro_sum),
            )

        head_match = sqlite_side.head_time == pg_side.head_time
        count_match = int(sqlite_side.count) == int(pg_side.count)
        checksum_match = bool(
            int(sqlite_side.candle_time_sum) == int(pg_side.candle_time_sum)
            and int(sqlite_side.close_micro_sum) == int(pg_side.close_micro_sum)
        )
        diff = ReconcileDiffSnapshot(
            head_match=bool(head_match),
            count_match=bool(count_match),
            checksum_match=bool(checksum_match),
            match=bool(head_match and count_match and checksum_match),
        )
        return ReconcileSeriesSnapshot(
            series_id=sid,
            range_start=range_start,
            range_end=range_end,
            sqlite=sqlite_side,
            postgres=pg_side,
            diff=diff,
        )
