from __future__ import annotations

from backend.app.ingest.reaper_policy import IngestReaperJobState, plan_ingest_reaper


def test_plan_ingest_reaper_returns_restart_stop_and_drop_sets() -> None:
    jobs = (
        IngestReaperJobState(
            series_id="binance:spot:BTC/USDT:1m",
            refcount=1,
            last_zero_at=None,
            task_done=True,
        ),
        IngestReaperJobState(
            series_id="binance:spot:ETH/USDT:1m",
            refcount=0,
            last_zero_at=5.0,
            task_done=False,
        ),
        IngestReaperJobState(
            series_id="binance:spot:XRP/USDT:1m",
            refcount=0,
            last_zero_at=None,
            task_done=True,
        ),
    )

    plan = plan_ingest_reaper(
        jobs=jobs,
        now=20.0,
        idle_ttl_s=10.0,
        is_pinned_whitelist=lambda series_id: series_id == "binance:spot:XRP/USDT:1m",
    )

    assert plan.restart_series_ids == (
        "binance:spot:BTC/USDT:1m",
        "binance:spot:XRP/USDT:1m",
    )
    assert plan.stop_series_ids == ("binance:spot:ETH/USDT:1m",)
    assert plan.drop_series_ids == ("binance:spot:ETH/USDT:1m",)


def test_plan_ingest_reaper_drops_dead_inactive_ondemand_job() -> None:
    jobs = (
        IngestReaperJobState(
            series_id="binance:spot:BTC/USDT:1m",
            refcount=0,
            last_zero_at=None,
            task_done=True,
        ),
    )

    plan = plan_ingest_reaper(
        jobs=jobs,
        now=20.0,
        idle_ttl_s=10.0,
        is_pinned_whitelist=lambda _series_id: False,
    )

    assert plan.restart_series_ids == ()
    assert plan.stop_series_ids == ()
    assert plan.drop_series_ids == ("binance:spot:BTC/USDT:1m",)
