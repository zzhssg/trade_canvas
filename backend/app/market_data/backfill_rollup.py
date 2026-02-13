from __future__ import annotations

from ..market.derived_timeframes import rollup_closed_candles
from ..core.series_id import SeriesId, parse_series_id
from ..storage.candle_store import CandleStore
from ..core.timeframe import timeframe_to_seconds


def best_effort_backfill_from_base_1m(
    *,
    store: CandleStore,
    series_id: str,
    start_time: int,
    end_time: int,
) -> int:
    try:
        series = parse_series_id(series_id)
    except ValueError:
        return 0
    if str(series.timeframe) == "1m":
        return 0

    derived_tf_s = timeframe_to_seconds(series.timeframe)
    base_tf_s = timeframe_to_seconds("1m")
    if derived_tf_s <= int(base_tf_s):
        return 0
    if derived_tf_s % int(base_tf_s) != 0:
        return 0
    if derived_tf_s > 900:
        return 0

    base_series_id = SeriesId(
        exchange=series.exchange,
        market=series.market,
        symbol=series.symbol,
        timeframe="1m",
    ).raw
    if store.head_time(base_series_id) is None:
        return 0

    base_start = max(0, int(start_time) - int(derived_tf_s) + int(base_tf_s))
    base_limit = max(20000, int((int(end_time) - int(base_start)) // int(base_tf_s)) + 16)
    base_candles = store.get_closed_between_times(
        base_series_id,
        start_time=int(base_start),
        end_time=int(end_time),
        limit=int(base_limit),
    )
    if not base_candles:
        return 0

    derived = rollup_closed_candles(
        base_timeframe="1m",
        derived_timeframe=series.timeframe,
        base_candles=base_candles,
    )
    if not derived:
        return 0
    write_batch = [c for c in derived if int(start_time) <= int(c.candle_time) <= int(end_time)]
    if not write_batch:
        return 0

    with store.connect() as conn:
        store.upsert_many_closed_in_conn(conn, series_id, write_batch)
        conn.commit()
    return len(write_batch)
