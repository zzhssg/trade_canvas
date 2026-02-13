from __future__ import annotations

import json
from typing import Any, Callable, Iterator

from ..factor.store import FactorEventRow


def row_get(row: Any, *, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (KeyError, IndexError):
            pass
    return row[index]


def json_load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def decode_event_rows(rows: list[Any]) -> list[FactorEventRow]:
    out: list[FactorEventRow] = []
    for row in rows:
        out.append(
            FactorEventRow(
                id=int(row_get(row, index=0, key="id")),
                series_id=str(row_get(row, index=1, key="series_id")),
                factor_name=str(row_get(row, index=2, key="factor_name")),
                candle_time=int(row_get(row, index=3, key="candle_time")),
                kind=str(row_get(row, index=4, key="kind")),
                event_key=str(row_get(row, index=5, key="event_key")),
                payload=json_load(row_get(row, index=6, key="payload_json")),
            )
        )
    return out


def get_events_between_times(
    *,
    connect: Callable[[], Any],
    events_table: str,
    series_id: str,
    factor_name: str | None,
    start_candle_time: int,
    end_candle_time: int,
    limit: int,
) -> list[FactorEventRow]:
    params: list[Any] = [
        str(series_id),
        int(start_candle_time),
        int(end_candle_time),
        int(limit),
    ]
    if factor_name:
        sql = f"""
            SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
            FROM {events_table}
            WHERE series_id = %s AND factor_name = %s AND candle_time >= %s AND candle_time <= %s
            ORDER BY candle_time ASC, id ASC
            LIMIT %s
        """
        params = [
            str(series_id),
            str(factor_name),
            int(start_candle_time),
            int(end_candle_time),
            int(limit),
        ]
    else:
        sql = f"""
            SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
            FROM {events_table}
            WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
            ORDER BY candle_time ASC, id ASC
            LIMIT %s
        """
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return decode_event_rows(rows)


def get_events_between_times_paged(
    *,
    connect: Callable[[], Any],
    events_table: str,
    series_id: str,
    factor_name: str | None,
    start_candle_time: int,
    end_candle_time: int,
    page_size: int,
) -> list[FactorEventRow]:
    return list(
        iter_events_between_times_paged(
            connect=connect,
            events_table=events_table,
            series_id=series_id,
            factor_name=factor_name,
            start_candle_time=start_candle_time,
            end_candle_time=end_candle_time,
            page_size=page_size,
        )
    )


def iter_events_between_times_paged(
    *,
    connect: Callable[[], Any],
    events_table: str,
    series_id: str,
    factor_name: str | None,
    start_candle_time: int,
    end_candle_time: int,
    page_size: int,
) -> Iterator[FactorEventRow]:
    size = max(1, int(page_size))
    with connect() as conn:
        last_time: int | None = None
        last_id = 0
        while True:
            params: tuple[Any, ...]
            if factor_name:
                if last_time is None:
                    sql = f"""
                        SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                        FROM {events_table}
                        WHERE series_id = %s AND factor_name = %s AND candle_time >= %s AND candle_time <= %s
                        ORDER BY candle_time ASC, id ASC
                        LIMIT %s
                    """
                    params = (
                        str(series_id),
                        str(factor_name),
                        int(start_candle_time),
                        int(end_candle_time),
                        int(size),
                    )
                else:
                    sql = f"""
                        SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                        FROM {events_table}
                        WHERE series_id = %s AND factor_name = %s AND candle_time >= %s AND candle_time <= %s
                          AND (candle_time > %s OR (candle_time = %s AND id > %s))
                        ORDER BY candle_time ASC, id ASC
                        LIMIT %s
                    """
                    params = (
                        str(series_id),
                        str(factor_name),
                        int(start_candle_time),
                        int(end_candle_time),
                        int(last_time),
                        int(last_time),
                        int(last_id),
                        int(size),
                    )
            else:
                if last_time is None:
                    sql = f"""
                        SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                        FROM {events_table}
                        WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
                        ORDER BY candle_time ASC, id ASC
                        LIMIT %s
                    """
                    params = (
                        str(series_id),
                        int(start_candle_time),
                        int(end_candle_time),
                        int(size),
                    )
                else:
                    sql = f"""
                        SELECT id, series_id, factor_name, candle_time, kind, event_key, payload_json
                        FROM {events_table}
                        WHERE series_id = %s AND candle_time >= %s AND candle_time <= %s
                          AND (candle_time > %s OR (candle_time = %s AND id > %s))
                        ORDER BY candle_time ASC, id ASC
                        LIMIT %s
                    """
                    params = (
                        str(series_id),
                        int(start_candle_time),
                        int(end_candle_time),
                        int(last_time),
                        int(last_time),
                        int(last_id),
                        int(size),
                    )
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                break
            decoded = decode_event_rows(rows)
            for item in decoded:
                yield item
            if len(rows) < size:
                break
            last = rows[-1]
            last_time = int(row_get(last, index=3, key="candle_time"))
            last_id = int(row_get(last, index=0, key="id"))
