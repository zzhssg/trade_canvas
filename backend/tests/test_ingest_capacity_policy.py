from __future__ import annotations

from dataclasses import dataclass

from backend.app.ingest.capacity_policy import plan_ondemand_capacity


@dataclass
class _JobState:
    series_id: str
    refcount: int
    last_zero_at: float | None


def test_plan_ondemand_capacity_accepts_when_under_limit() -> None:
    jobs = (
        _JobState(series_id="binance:spot:BTC/USDT:1m", refcount=1, last_zero_at=None),
    )

    plan = plan_ondemand_capacity(
        jobs=jobs,
        max_jobs=2,
        is_pinned_whitelist=lambda _sid: False,
        now=100.0,
    )

    assert plan.accepted is True
    assert plan.victim_series_id is None


def test_plan_ondemand_capacity_rejects_when_full_without_idle_jobs() -> None:
    jobs = (
        _JobState(series_id="binance:spot:BTC/USDT:1m", refcount=1, last_zero_at=None),
    )

    plan = plan_ondemand_capacity(
        jobs=jobs,
        max_jobs=1,
        is_pinned_whitelist=lambda _sid: False,
        now=100.0,
    )

    assert plan.accepted is False
    assert plan.victim_series_id is None


def test_plan_ondemand_capacity_evicts_oldest_idle_job() -> None:
    jobs = (
        _JobState(series_id="binance:spot:BTC/USDT:1m", refcount=0, last_zero_at=10.0),
        _JobState(series_id="binance:spot:ETH/USDT:1m", refcount=0, last_zero_at=30.0),
    )

    plan = plan_ondemand_capacity(
        jobs=jobs,
        max_jobs=1,
        is_pinned_whitelist=lambda _sid: False,
        now=100.0,
    )

    assert plan.accepted is True
    assert plan.victim_series_id == "binance:spot:BTC/USDT:1m"
