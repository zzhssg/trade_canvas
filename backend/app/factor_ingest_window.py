from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _CandleStoreLike(Protocol):
    def first_time(self, series_id: str) -> int | None: ...

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int: ...

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[Any]: ...


@dataclass(frozen=True)
class FactorIngestWindowPlan:
    lookback_candles: int
    start_time: int
    read_limit: int


@dataclass(frozen=True)
class FactorIngestCandleBatch:
    candles: list[Any]
    time_to_idx: dict[int, int]
    process_times: list[int]


class FactorIngestWindowPlanner:
    def __init__(self, *, candle_store: _CandleStoreLike) -> None:
        self._candle_store = candle_store

    def plan_window(
        self,
        *,
        series_id: str,
        up_to: int,
        head_time: int,
        tf_s: int,
        settings_lookback_candles: int,
        max_window: int,
        force_rebuild_from_earliest: bool,
    ) -> FactorIngestWindowPlan | None:
        lookback_candles = int(settings_lookback_candles) + int(max_window) * 2 + 5

        if bool(force_rebuild_from_earliest):
            earliest = self._candle_store.first_time(series_id)
            if earliest is None:
                return None
            start_time = int(earliest)
            total = self._candle_store.count_closed_between_times(
                series_id,
                start_time=int(start_time),
                end_time=int(up_to),
            )
            read_limit = max(int(total) + 10, int(lookback_candles) + 10)
            return FactorIngestWindowPlan(
                lookback_candles=int(lookback_candles),
                start_time=int(start_time),
                read_limit=int(read_limit),
            )

        start_time = max(0, int(up_to) - int(lookback_candles) * int(tf_s))
        if int(head_time) > 0:
            start_time = max(0, min(int(start_time), int(head_time) - int(max_window) * 2 * int(tf_s)))
        read_limit = int(lookback_candles) + 10
        return FactorIngestWindowPlan(
            lookback_candles=int(lookback_candles),
            start_time=int(start_time),
            read_limit=int(read_limit),
        )

    def load_candle_batch(
        self,
        *,
        series_id: str,
        up_to: int,
        head_time: int,
        plan: FactorIngestWindowPlan,
    ) -> FactorIngestCandleBatch | None:
        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(plan.start_time),
            end_time=int(up_to),
            limit=int(plan.read_limit),
        )
        if not candles:
            return None

        candle_times = [int(c.candle_time) for c in candles]
        time_to_idx = {int(t): int(i) for i, t in enumerate(candle_times)}
        process_times = [t for t in candle_times if int(t) > int(head_time) and int(t) <= int(up_to)]
        if not process_times:
            return None

        return FactorIngestCandleBatch(
            candles=candles,
            time_to_idx=time_to_idx,
            process_times=process_times,
        )
