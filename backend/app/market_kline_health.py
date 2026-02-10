from __future__ import annotations

import time
from typing import Any

from .series_id import SeriesId, parse_series_id
from .store import CandleStore
from .timeframe import timeframe_to_seconds


def _base_series_id(series: SeriesId) -> str:
    return SeriesId(
        exchange=series.exchange,
        market=series.market,
        symbol=series.symbol,
        timeframe="1m",
    ).raw


def _query_recent_gaps(
    *,
    store: CandleStore,
    series_id: str,
    timeframe_s: int,
    limit: int,
) -> tuple[int, int | None, list[dict[str, int]]]:
    sql = """
    WITH ordered AS (
      SELECT
        candle_time,
        LAG(candle_time) OVER (ORDER BY candle_time) AS prev_time
      FROM candles
      WHERE series_id = ?
    ),
    gaps AS (
      SELECT
        prev_time,
        candle_time AS next_time,
        candle_time - prev_time AS delta_seconds
      FROM ordered
      WHERE prev_time IS NOT NULL AND candle_time - prev_time > ?
    )
    SELECT prev_time, next_time, delta_seconds
    FROM gaps
    ORDER BY next_time DESC
    LIMIT ?
    """
    with store.connect() as conn:
        rows = conn.execute(sql, (series_id, int(timeframe_s), int(limit))).fetchall()
        stat_row = conn.execute(
            """
            WITH ordered AS (
              SELECT
                candle_time,
                LAG(candle_time) OVER (ORDER BY candle_time) AS prev_time
              FROM candles
              WHERE series_id = ?
            )
            SELECT
              COUNT(*) AS gap_count,
              MAX(candle_time - prev_time) AS max_gap_seconds
            FROM ordered
            WHERE prev_time IS NOT NULL AND candle_time - prev_time > ?
            """,
            (series_id, int(timeframe_s)),
        ).fetchone()

    recent = [
        {
            "prev_time": int(r["prev_time"]),
            "next_time": int(r["next_time"]),
            "delta_seconds": int(r["delta_seconds"]),
            "missing_candles": max(0, int(r["delta_seconds"] // int(timeframe_s) - 1)),
        }
        for r in rows
    ]
    gap_count = int(stat_row["gap_count"]) if stat_row and stat_row["gap_count"] is not None else 0
    max_gap_seconds = int(stat_row["max_gap_seconds"]) if stat_row and stat_row["max_gap_seconds"] is not None else None
    return gap_count, max_gap_seconds, recent


def _query_recent_bucket_completeness(
    *,
    store: CandleStore,
    series: SeriesId,
    timeframe_s: int,
    buckets: int,
) -> list[dict[str, int]]:
    if int(timeframe_s) <= 60:
        return []

    base_series_id = _base_series_id(series)
    base_head = store.head_time(base_series_id)
    if base_head is None:
        return []

    base_step = 60
    expected = int(timeframe_s // base_step)
    end_bucket = int(base_head // int(timeframe_s)) * int(timeframe_s)
    start_bucket = max(0, int(end_bucket) - max(0, int(buckets) - 1) * int(timeframe_s))
    base_start = max(0, int(start_bucket) - int(timeframe_s) + int(base_step))

    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT candle_time
            FROM candles
            WHERE series_id = ? AND candle_time >= ? AND candle_time <= ?
            ORDER BY candle_time ASC
            """,
            (base_series_id, int(base_start), int(end_bucket + timeframe_s)),
        ).fetchall()

    base_times = {int(r["candle_time"]) for r in rows}
    out: list[dict[str, int]] = []
    for bucket_open in range(int(start_bucket), int(end_bucket) + 1, int(timeframe_s)):
        have = 0
        for i in range(expected):
            t = int(bucket_open) + int(i) * int(base_step)
            if t in base_times:
                have += 1
        out.append(
            {
                "bucket_open_time": int(bucket_open),
                "expected_minutes": int(expected),
                "actual_minutes": int(have),
                "missing_minutes": max(0, int(expected) - int(have)),
            }
        )
    return out


def analyze_series_health(
    *,
    store: CandleStore,
    series_id: str,
    now_time: int | None = None,
    max_recent_gaps: int = 5,
    recent_base_buckets: int = 8,
) -> dict[str, Any]:
    series = parse_series_id(series_id)
    timeframe_s = int(timeframe_to_seconds(series.timeframe))
    now = int(now_time) if now_time is not None else int(time.time())

    with store.connect() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS candle_count,
              MIN(candle_time) AS first_time,
              MAX(candle_time) AS head_time
            FROM candles
            WHERE series_id = ?
            """,
            (series_id,),
        ).fetchone()

    candle_count = int(row["candle_count"]) if row and row["candle_count"] is not None else 0
    first_time = int(row["first_time"]) if row and row["first_time"] is not None else None
    head_time = int(row["head_time"]) if row and row["head_time"] is not None else None
    lag_seconds = None if head_time is None else max(0, int(now) - int(head_time))

    gap_count, max_gap_seconds, recent_gaps = _query_recent_gaps(
        store=store,
        series_id=series_id,
        timeframe_s=timeframe_s,
        limit=max(1, int(max_recent_gaps)),
    )

    base_bucket_completeness = _query_recent_bucket_completeness(
        store=store,
        series=series,
        timeframe_s=timeframe_s,
        buckets=max(1, int(recent_base_buckets)),
    )

    return {
        "series_id": series_id,
        "timeframe_seconds": int(timeframe_s),
        "now_time": int(now),
        "first_time": first_time,
        "head_time": head_time,
        "lag_seconds": lag_seconds,
        "candle_count": int(candle_count),
        "gap_count": int(gap_count),
        "max_gap_seconds": max_gap_seconds,
        "recent_gaps": recent_gaps,
        "base_series_id": _base_series_id(series),
        "base_bucket_completeness": base_bucket_completeness,
    }
