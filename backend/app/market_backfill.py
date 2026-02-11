from __future__ import annotations

import time

from .ccxt_client import _make_exchange_client, ccxt_symbol_for_series
from .history_bootstrapper import backfill_tail_from_freqtrade
from .schemas import CandleClosed
from .series_id import parse_series_id
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def backfill_from_ccxt_range(
    *,
    candle_store: CandleStore,
    series_id: str,
    start_time: int,
    end_time: int,
    batch_limit: int = 1000,
    ccxt_timeout_ms: int = 10_000,
) -> int:
    """
    Best-effort CCXT backfill for [start_time, end_time] (inclusive).
    Returns number of rows written (upsert count).
    """
    if int(end_time) < int(start_time):
        return 0

    try:
        series = parse_series_id(series_id)
    except Exception:
        return 0

    tf_s = timeframe_to_seconds(series.timeframe)
    start = max(0, int(start_time))
    end = int(end_time)
    if end <= 0:
        end = int(time.time() // int(tf_s) * int(tf_s))

    exchange = _make_exchange_client(series, timeout_ms=int(ccxt_timeout_ms))
    symbol = ccxt_symbol_for_series(series)
    since_ms = int(start * 1000)
    total_written = 0

    try:
        while since_ms <= int(end * 1000):
            rows = exchange.fetch_ohlcv(symbol, series.timeframe, since_ms, int(batch_limit))
            if not rows:
                break

            to_write: list[CandleClosed] = []
            max_open_time_s: int | None = None

            for row in rows:
                open_time_s = int(row[0] // 1000)
                max_open_time_s = open_time_s if max_open_time_s is None else max(max_open_time_s, open_time_s)
                if open_time_s < start or open_time_s > end:
                    continue
                to_write.append(
                    CandleClosed(
                        candle_time=open_time_s,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )

            if to_write:
                with candle_store.connect() as conn:
                    candle_store.upsert_many_closed_in_conn(conn, series_id, to_write)
                    conn.commit()
                total_written += len(to_write)

            if max_open_time_s is None:
                break
            if max_open_time_s >= end:
                break

            next_since_ms = int((max_open_time_s + int(tf_s)) * 1000)
            if next_since_ms <= since_ms:
                break
            since_ms = next_since_ms
    finally:
        try:
            close = getattr(exchange, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    return total_written


def backfill_market_gap_best_effort(
    *,
    store: CandleStore,
    series_id: str,
    expected_next_time: int,
    actual_time: int,
    enable_ccxt_backfill: bool = False,
    freqtrade_limit: int = 2000,
    market_history_source: str = "",
    ccxt_timeout_ms: int = 10_000,
) -> int:
    """
    Best-effort gap backfill for realtime market stream.

    Gap range is [expected_next_time, actual_time - timeframe].
    Returns newly available candle count in that range.
    """
    tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    start = int(expected_next_time)
    end = int(actual_time) - int(tf_s)
    if end < start:
        return 0

    before = store.count_closed_between_times(series_id, start_time=start, end_time=end)

    base_limit = max(1, int(freqtrade_limit))

    target_candles = ((end - start) // int(tf_s)) + 1
    freqtrade_limit = max(base_limit, int(target_candles) + 8)

    try:
        backfill_tail_from_freqtrade(
            store,
            series_id=series_id,
            limit=int(freqtrade_limit),
            market_history_source=str(market_history_source),
        )
    except Exception:
        pass

    if bool(enable_ccxt_backfill):
        try:
            backfill_from_ccxt_range(
                candle_store=store,
                series_id=series_id,
                start_time=int(start),
                end_time=int(end),
                ccxt_timeout_ms=int(ccxt_timeout_ms),
            )
        except Exception:
            pass

    after = store.count_closed_between_times(series_id, start_time=start, end_time=end)
    return max(0, int(after) - int(before))
