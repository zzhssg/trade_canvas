from __future__ import annotations

from collections import deque
import time
from typing import Any, Iterator

from ..series_id import SeriesId, parse_series_id
from ..store import CandleStore
from ..timeframe import timeframe_to_seconds


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
    recent: deque[dict[str, int]] = deque(maxlen=max(1, int(limit)))
    gap_count = 0
    max_gap_seconds: int | None = None
    prev_time: int | None = None
    for candle_time in _iter_series_candle_times(store=store, series_id=series_id):
        if prev_time is None:
            prev_time = int(candle_time)
            continue
        delta_seconds = int(candle_time) - int(prev_time)
        if delta_seconds > int(timeframe_s):
            gap_count += 1
            max_gap_seconds = (
                int(delta_seconds)
                if max_gap_seconds is None
                else max(int(max_gap_seconds), int(delta_seconds))
            )
            recent.append(
                {
                    "prev_time": int(prev_time),
                    "next_time": int(candle_time),
                    "delta_seconds": int(delta_seconds),
                    "missing_candles": max(0, int(delta_seconds // int(timeframe_s) - 1)),
                }
            )
        prev_time = int(candle_time)

    recent_list = list(recent)
    recent_list.reverse()
    return gap_count, max_gap_seconds, recent_list


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
    base_limit = max(
        128,
        int((int(end_bucket + timeframe_s) - int(base_start)) // int(base_step)) + 16,
    )
    base_rows = store.get_closed_between_times(
        base_series_id,
        start_time=int(base_start),
        end_time=int(end_bucket + timeframe_s),
        limit=int(base_limit),
    )
    base_times = {int(c.candle_time) for c in base_rows}
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
    first_time = store.first_time(series_id)
    head_time = store.head_time(series_id)
    if first_time is None or head_time is None:
        candle_count = 0
    else:
        candle_count = store.count_closed_between_times(
            series_id,
            start_time=int(first_time),
            end_time=int(head_time),
        )
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


def _iter_series_candle_times(
    *,
    store: CandleStore,
    series_id: str,
    page_size: int = 5000,
) -> Iterator[int]:
    first_time = store.first_time(series_id)
    if first_time is None:
        return
    size = max(1, int(page_size))
    cursor = int(first_time) - 1
    while True:
        batch = store.get_closed(series_id, since=int(cursor), limit=int(size))
        if not batch:
            return
        for candle in batch:
            yield int(candle.candle_time)
        last_time = int(batch[-1].candle_time)
        if len(batch) < size or int(last_time) <= int(cursor):
            return
        cursor = int(last_time)
