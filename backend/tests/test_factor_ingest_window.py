from __future__ import annotations

from dataclasses import dataclass

from backend.app.factor.ingest_window import FactorIngestWindowPlan, FactorIngestWindowPlanner
from backend.app.core.schemas import CandleClosed


@dataclass
class _CandleStoreStub:
    earliest: int | None = None
    total_between: int = 0
    candles: list[CandleClosed] | None = None

    def first_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return None if self.earliest is None else int(self.earliest)

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:  # noqa: ARG002
        _ = start_time
        _ = end_time
        return int(self.total_between)

    def get_closed_between_times(
        self,
        series_id: str,  # noqa: ARG002
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        _ = start_time
        _ = end_time
        _ = limit
        return list(self.candles or [])


def _candles(times: list[int]) -> list[CandleClosed]:
    return [
        CandleClosed(
            candle_time=int(t),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        for t in times
    ]


def test_plan_window_returns_none_when_force_rebuild_without_earliest() -> None:
    planner = FactorIngestWindowPlanner(candle_store=_CandleStoreStub(earliest=None))
    plan = planner.plan_window(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=600,
        head_time=0,
        tf_s=60,
        settings_lookback_candles=200,
        max_window=50,
        force_rebuild_from_earliest=True,
    )
    assert plan is None


def test_plan_window_force_rebuild_uses_total_and_lookback_limit() -> None:
    planner = FactorIngestWindowPlanner(candle_store=_CandleStoreStub(earliest=120, total_between=30))
    plan = planner.plan_window(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=1000,
        head_time=0,
        tf_s=60,
        settings_lookback_candles=200,
        max_window=10,
        force_rebuild_from_earliest=True,
    )
    assert plan is not None
    assert plan.start_time == 120
    assert plan.lookback_candles == 225
    assert plan.read_limit == 235


def test_plan_window_incremental_clamps_start_time_by_head() -> None:
    planner = FactorIngestWindowPlanner(candle_store=_CandleStoreStub())
    plan = planner.plan_window(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=10_000,
        head_time=4_000,
        tf_s=60,
        settings_lookback_candles=200,
        max_window=50,
        force_rebuild_from_earliest=False,
    )
    assert plan is not None
    assert plan.lookback_candles == 305
    assert plan.start_time == 0
    assert plan.read_limit == 315


def test_load_candle_batch_builds_process_times_and_time_index() -> None:
    store = _CandleStoreStub(candles=_candles([60, 120, 180, 240]))
    planner = FactorIngestWindowPlanner(candle_store=store)
    batch = planner.load_candle_batch(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=220,
        head_time=120,
        plan=FactorIngestWindowPlan(lookback_candles=200, start_time=0, read_limit=100),
    )
    assert batch is not None
    assert [int(c.candle_time) for c in batch.candles] == [60, 120, 180, 240]
    assert batch.time_to_idx == {60: 0, 120: 1, 180: 2, 240: 3}
    assert batch.process_times == [180]


def test_load_candle_batch_returns_none_when_no_process_times() -> None:
    store = _CandleStoreStub(candles=_candles([60, 120]))
    planner = FactorIngestWindowPlanner(candle_store=store)
    batch = planner.load_candle_batch(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=120,
        head_time=120,
        plan=FactorIngestWindowPlan(lookback_candles=200, start_time=0, read_limit=100),
    )
    assert batch is None
