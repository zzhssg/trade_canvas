from __future__ import annotations

import time
from typing import Callable

from ..derived_timeframes import rollup_closed_candles
from ..market_backfill import backfill_from_ccxt_range, backfill_market_gap_best_effort
from ..market_flags import ccxt_backfill_enabled, ccxt_backfill_on_read_enabled
from ..history_bootstrapper import backfill_tail_from_freqtrade
from ..schemas import CandleClosed
from ..series_id import SeriesId, parse_series_id
from ..store import CandleStore
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from .contracts import (
    BackfillGapRequest,
    BackfillGapResult,
    BackfillService,
    CandleReadService,
    FreshnessService,
    FreshnessSnapshot,
    FreshnessState,
)


class StoreCandleReadService(CandleReadService):
    def __init__(self, *, store: CandleStore) -> None:
        self._store = store

    def read_tail(self, *, series_id: str, limit: int) -> list[CandleClosed]:
        return self._store.get_closed(series_id, since=None, limit=int(limit))

    def read_incremental(self, *, series_id: str, since: int, limit: int) -> list[CandleClosed]:
        return self._store.get_closed(series_id, since=int(since), limit=int(limit))

    def read_between(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
        limit: int,
    ) -> list[CandleClosed]:
        return self._store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(end_time),
            limit=int(limit),
        )


class StoreBackfillService(BackfillService):
    def __init__(
        self,
        *,
        store: CandleStore,
        gap_backfill_fn: Callable[..., int] = backfill_market_gap_best_effort,
        tail_backfill_fn: Callable[..., int] = backfill_tail_from_freqtrade,
    ) -> None:
        self._store = store
        self._gap_backfill_fn = gap_backfill_fn
        self._tail_backfill_fn = tail_backfill_fn

    def _best_effort_backfill_from_base_1m(
        self,
        *,
        series_id: str,
        start_time: int,
        end_time: int,
    ) -> int:
        try:
            series = parse_series_id(series_id)
        except Exception:
            return 0
        if str(series.timeframe) == "1m":
            return 0

        derived_tf_s = timeframe_to_seconds(series.timeframe)
        base_tf_s = timeframe_to_seconds("1m")
        if derived_tf_s <= int(base_tf_s):
            return 0
        if derived_tf_s % int(base_tf_s) != 0:
            return 0
        # Keep scope tight for market live charting; avoid very wide local rollups.
        if derived_tf_s > 900:
            return 0

        base_series_id = SeriesId(
            exchange=series.exchange,
            market=series.market,
            symbol=series.symbol,
            timeframe="1m",
        ).raw
        if self._store.head_time(base_series_id) is None:
            return 0

        base_start = max(0, int(start_time) - int(derived_tf_s) + int(base_tf_s))
        base_limit = max(20000, int((int(end_time) - int(base_start)) // int(base_tf_s)) + 16)
        base_candles = self._store.get_closed_between_times(
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

        with self._store.connect() as conn:
            self._store.upsert_many_closed_in_conn(conn, series_id, write_batch)
            conn.commit()
        return len(write_batch)

    def backfill_gap(self, req: BackfillGapRequest) -> BackfillGapResult:
        filled = int(
            self._gap_backfill_fn(
                store=self._store,
                series_id=req.series_id,
                expected_next_time=int(req.expected_next_time),
                actual_time=int(req.actual_time),
            )
        )
        return BackfillGapResult(
            series_id=req.series_id,
            expected_next_time=int(req.expected_next_time),
            actual_time=int(req.actual_time),
            filled_count=max(0, filled),
        )

    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int:
        target = int(target_candles)
        if target <= 0:
            return 0
        try:
            filled = max(0, int(self._tail_backfill_fn(self._store, series_id=series_id, limit=target)))
        except Exception:
            filled = 0

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        if to_time is None:
            now = int(time.time())
            end_time = int(now // int(tf_s)) * int(tf_s)
        else:
            end_time = int(to_time)
        start_time = max(0, int(end_time) - (int(target) - 1) * int(tf_s))

        try:
            count_after_tail = self._store.count_closed_between_times(series_id, start_time=start_time, end_time=end_time)
        except Exception:
            count_after_tail = 0
        if int(count_after_tail) < int(target):
            try:
                self._best_effort_backfill_from_base_1m(
                    series_id=series_id,
                    start_time=int(start_time),
                    end_time=int(end_time),
                )
                count_after_tail = self._store.count_closed_between_times(
                    series_id,
                    start_time=start_time,
                    end_time=end_time,
                )
            except Exception:
                pass

        allow_ccxt = bool(to_time is not None) or ccxt_backfill_on_read_enabled()
        if int(count_after_tail) < int(target) and ccxt_backfill_enabled() and allow_ccxt:
            try:
                backfill_from_ccxt_range(
                    candle_store=self._store,
                    series_id=series_id,
                    start_time=int(start_time),
                    end_time=int(end_time),
                )
            except Exception:
                pass

        try:
            covered = self._store.count_closed_between_times(series_id, start_time=start_time, end_time=end_time)
        except Exception:
            covered = 0
        if to_time is None:
            return max(int(filled), int(covered))
        return int(covered)


class StoreFreshnessService(FreshnessService):
    def __init__(
        self,
        *,
        store: CandleStore,
        fresh_window_candles: int = 2,
        stale_window_candles: int = 5,
        now_fn: Callable[[], int] | None = None,
    ) -> None:
        self._store = store
        self._fresh_window_candles = max(1, int(fresh_window_candles))
        self._stale_window_candles = max(self._fresh_window_candles + 1, int(stale_window_candles))
        self._now_fn = now_fn or (lambda: int(time.time()))

    @staticmethod
    def _resolve_timeframe_seconds(series_id: str) -> int | None:
        try:
            timeframe = parse_series_id(series_id).timeframe
            return int(timeframe_to_seconds(timeframe))
        except Exception:
            return None

    def snapshot(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot:
        now = int(now_time) if now_time is not None else int(self._now_fn())
        head_time = self._store.head_time(series_id)
        if head_time is None:
            return FreshnessSnapshot(
                series_id=series_id,
                head_time=None,
                now_time=now,
                lag_seconds=None,
                state="missing",
            )

        lag = max(0, int(now) - int(head_time))
        tf_s = self._resolve_timeframe_seconds(series_id)
        state: FreshnessState
        if tf_s is None or tf_s <= 0:
            state = "degraded"
        else:
            fresh_lag_max = int(tf_s) * int(self._fresh_window_candles)
            stale_lag_max = int(tf_s) * int(self._stale_window_candles)
            if lag <= fresh_lag_max:
                state = "fresh"
            elif lag <= stale_lag_max:
                state = "stale"
            else:
                state = "degraded"

        return FreshnessSnapshot(
            series_id=series_id,
            head_time=int(head_time),
            now_time=now,
            lag_seconds=lag,
            state=state,
        )
