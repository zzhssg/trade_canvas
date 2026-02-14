from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from typing import Any, Iterator

from ..factor.store import (
    FactorEventRow,
    FactorEventWrite,
    FactorHeadSnapshotRow,
    FactorSeriesFingerprintRow,
)
from .contracts import DbConnection
from .postgres_factor_events import (
    get_events_between_times,
    get_events_between_times_paged,
    iter_events_between_times_paged,
    json_load,
    row_get,
)
from .postgres_common import normalize_identifier, query_series_head_time, upsert_series_head_time
from .postgres_pool import PostgresPool


class PostgresFactorRepository:
    _pool: PostgresPool
    _schema: str
    _series_state_table: str
    _events_table: str
    _head_snapshots_table: str
    _series_fingerprint_table: str

    def __init__(self, *, pool: PostgresPool, schema: str) -> None:
        object.__setattr__(self, "_pool", pool)
        schema_name = normalize_identifier(schema, key="schema")
        object.__setattr__(self, "_schema", schema_name)
        object.__setattr__(self, "_series_state_table", f"{schema_name}.factor_series_state")
        object.__setattr__(self, "_events_table", f"{schema_name}.factor_events")
        object.__setattr__(self, "_head_snapshots_table", f"{schema_name}.factor_head_snapshots")
        object.__setattr__(self, "_series_fingerprint_table", f"{schema_name}.factor_series_fingerprint")

    def connect(self) -> AbstractContextManager[DbConnection]:
        return self._pool.connect()

    def upsert_head_time_in_conn(self, conn: DbConnection, *, series_id: str, head_time: int) -> None:
        upsert_series_head_time(
            conn,
            series_state_table=self._series_state_table,
            series_id=series_id,
            head_time=head_time,
        )

    def head_time(self, series_id: str) -> int | None:
        with self.connect() as conn:
            return query_series_head_time(
                conn,
                series_state_table=self._series_state_table,
                series_id=series_id,
            )

    def get_series_fingerprint(self, series_id: str) -> FactorSeriesFingerprintRow | None:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT series_id, fingerprint, updated_at_ms
                FROM {self._series_fingerprint_table}
                WHERE series_id = %s
                """,
                (str(series_id),),
            ).fetchone()
        if row is None:
            return None
        return FactorSeriesFingerprintRow(
            series_id=str(row_get(row, index=0, key="series_id")),
            fingerprint=str(row_get(row, index=1, key="fingerprint")),
            updated_at_ms=int(row_get(row, index=2, key="updated_at_ms")),
        )

    def upsert_series_fingerprint_in_conn(self, conn: DbConnection, *, series_id: str, fingerprint: str) -> None:
        now_ms = int(time.time() * 1000)
        conn.execute(
            f"""
            INSERT INTO {self._series_fingerprint_table}(series_id, fingerprint, updated_at_ms)
            VALUES (%s, %s, %s)
            ON CONFLICT(series_id) DO UPDATE SET
              fingerprint=EXCLUDED.fingerprint,
              updated_at_ms=EXCLUDED.updated_at_ms
            """,
            (str(series_id), str(fingerprint), now_ms),
        )

    def clear_series_in_conn(self, conn: DbConnection, *, series_id: str) -> None:
        sid = str(series_id)
        conn.execute(f"DELETE FROM {self._events_table} WHERE series_id = %s", (sid,))
        conn.execute(f"DELETE FROM {self._head_snapshots_table} WHERE series_id = %s", (sid,))
        conn.execute(f"DELETE FROM {self._series_state_table} WHERE series_id = %s", (sid,))

    def last_event_id(self, series_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT MAX(id) AS v FROM {self._events_table} WHERE series_id = %s",
                (str(series_id),),
            ).fetchone()
        if row is None:
            return 0
        value = row_get(row, index=0, key="v")
        return 0 if value is None else int(value)

    def insert_events_in_conn(self, conn: DbConnection, *, events: list[FactorEventWrite]) -> None:
        if not events:
            return
        now_ms = int(time.time() * 1000)
        for event in events:
            conn.execute(
                f"""
                INSERT INTO {self._events_table}(
                  series_id, factor_name, candle_time, kind, event_key, payload_json, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT(series_id, factor_name, event_key) DO NOTHING
                """,
                (
                    str(event.series_id),
                    str(event.factor_name),
                    int(event.candle_time),
                    str(event.kind),
                    str(event.event_key),
                    json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    now_ms,
                ),
            )

    def insert_head_snapshot_in_conn(
        self,
        conn: DbConnection,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
        head: dict[str, Any],
    ) -> int | None:
        if head is None:
            return None
        row = conn.execute(
            f"""
            SELECT seq, head_json
            FROM {self._head_snapshots_table}
            WHERE series_id = %s AND factor_name = %s AND candle_time = %s
            ORDER BY seq DESC
            LIMIT 1
            """,
            (str(series_id), str(factor_name), int(candle_time)),
        ).fetchone()
        if row is not None:
            prev = json_load(row_get(row, index=1, key="head_json"))
            if prev == head:
                return int(row_get(row, index=0, key="seq"))
            next_seq = int(row_get(row, index=0, key="seq")) + 1
        else:
            next_seq = 0

        now_ms = int(time.time() * 1000)
        conn.execute(
            f"""
            INSERT INTO {self._head_snapshots_table}(
              series_id, factor_name, candle_time, seq, head_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(series_id),
                str(factor_name),
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
                f"""
                SELECT id, series_id, factor_name, candle_time, seq, head_json
                FROM {self._head_snapshots_table}
                WHERE series_id = %s AND factor_name = %s AND candle_time <= %s
                ORDER BY candle_time DESC, seq DESC
                LIMIT 1
                """,
                (str(series_id), str(factor_name), int(candle_time)),
            ).fetchone()
        if row is None:
            return None
        return FactorHeadSnapshotRow(
            id=int(row_get(row, index=0, key="id")),
            series_id=str(row_get(row, index=1, key="series_id")),
            factor_name=str(row_get(row, index=2, key="factor_name")),
            candle_time=int(row_get(row, index=3, key="candle_time")),
            seq=int(row_get(row, index=4, key="seq")),
            head=json_load(row_get(row, index=5, key="head_json")),
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
        return get_events_between_times(
            connect=self.connect,
            events_table=self._events_table,
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=start_candle_time,
            end_candle_time=end_candle_time,
            limit=limit,
        )

    def get_events_between_times_paged(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        page_size: int = 20000,
    ) -> list[FactorEventRow]:
        return get_events_between_times_paged(
            connect=self.connect,
            events_table=self._events_table,
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=start_candle_time,
            end_candle_time=end_candle_time,
            page_size=page_size,
        )

    def iter_events_between_times_paged(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        page_size: int = 20000,
    ) -> Iterator[FactorEventRow]:
        yield from iter_events_between_times_paged(
            connect=self.connect,
            events_table=self._events_table,
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=start_candle_time,
            end_candle_time=end_candle_time,
            page_size=page_size,
        )
