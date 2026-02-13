from __future__ import annotations

from backend.app.core.timeframe import expected_latest_closed_time, timeframe_to_seconds


def test_expected_latest_closed_time_uses_previous_closed_bucket() -> None:
    tf_s = timeframe_to_seconds("1m")
    assert expected_latest_closed_time(now_time=1735689665, timeframe_seconds=tf_s) == 1735689600


def test_expected_latest_closed_time_at_exact_boundary_steps_back_one_bucket() -> None:
    tf_s = timeframe_to_seconds("5m")
    assert expected_latest_closed_time(now_time=1700000100, timeframe_seconds=tf_s) == 1699999800


def test_expected_latest_closed_time_before_first_bucket_returns_zero() -> None:
    tf_s = timeframe_to_seconds("1h")
    assert expected_latest_closed_time(now_time=1200, timeframe_seconds=tf_s) == 0


def test_expected_latest_closed_time_handles_non_positive_timeframe_seconds() -> None:
    assert expected_latest_closed_time(now_time=4000, timeframe_seconds=0) == 3999
    assert expected_latest_closed_time(now_time=4000, timeframe_seconds=-5) == 3999


def test_expected_latest_closed_time_zero_now_returns_zero() -> None:
    tf_s = timeframe_to_seconds("1d")
    assert expected_latest_closed_time(now_time=0, timeframe_seconds=tf_s) == 0
