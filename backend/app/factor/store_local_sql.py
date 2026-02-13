from __future__ import annotations

import json
from typing import Any

from ..storage.local_store_runtime import LocalConnectionBase, MemoryCursor


def execute_local_factor_sql(
    *,
    conn: LocalConnectionBase,
    state: Any,
    sql: str,
    params: tuple[Any, ...] | list[Any] = (),
) -> MemoryCursor:
    from .store import FactorEventRow

    normalized = " ".join(str(sql).strip().split()).lower()
    values = tuple(params)

    if (
        normalized.startswith("select payload_json from factor_events")
        and "factor_name = 'pen'" in normalized
        and "kind = 'pen.confirmed'" in normalized
    ):
        series_id = str(values[0]) if values else ""
        rows = [
            conn.build_row(
                {
                    "payload_json": json.dumps(
                        event.payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                }
            )
            for event in sorted(state.events, key=lambda row: int(row.id))
            if str(event.series_id) == series_id
            and str(event.factor_name) == "pen"
            and str(event.kind) == "pen.confirmed"
        ]
        return MemoryCursor(rows=rows, rowcount=len(rows))

    if (
        normalized.startswith("select id, payload_json from factor_events")
        and "factor_name = 'zhongshu'" in normalized
        and "kind = 'zhongshu.dead'" in normalized
    ):
        series_id = str(values[0]) if values else ""
        rows = [
            conn.build_row(
                {
                    "id": int(event.id),
                    "payload_json": json.dumps(
                        event.payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                },
                order=("id", "payload_json"),
            )
            for event in sorted(state.events, key=lambda row: int(row.id))
            if str(event.series_id) == series_id
            and str(event.factor_name) == "zhongshu"
            and str(event.kind) == "zhongshu.dead"
        ]
        return MemoryCursor(rows=rows, rowcount=len(rows))

    if normalized.startswith("update factor_events set payload_json = ? where id = ?"):
        payload_text = str(values[0]) if values else "{}"
        event_id = int(values[1]) if len(values) > 1 else 0
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        rowcount = 0
        updated_events: list[Any] = []
        for event in state.events:
            if int(event.id) == int(event_id):
                updated_events.append(
                    FactorEventRow(
                        id=int(event.id),
                        series_id=event.series_id,
                        factor_name=event.factor_name,
                        candle_time=int(event.candle_time),
                        kind=event.kind,
                        event_key=event.event_key,
                        payload=dict(payload),
                    )
                )
                rowcount = 1
            else:
                updated_events.append(event)
        if rowcount > 0:
            state.events = updated_events
            conn.total_changes += int(rowcount)
        return MemoryCursor(rowcount=rowcount)

    if normalized.startswith(
        "select count(1) as c from factor_head_snapshots where series_id = ? and factor_name = ?"
    ):
        series_id = str(values[0]) if values else ""
        factor_name = str(values[1]) if len(values) > 1 else ""
        count = sum(
            1
            for row in state.head_snapshots
            if str(row.series_id) == series_id and str(row.factor_name) == factor_name
        )
        return MemoryCursor(rows=[conn.build_row({"c": int(count)})], rowcount=1)

    raise RuntimeError(f"unsupported_local_store_sql:{sql.strip()[:96]}")
