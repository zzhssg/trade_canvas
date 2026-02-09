from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.packages.calendar_engine.service import CalendarService
from trade_oracle.packages.calendar_engine.solar_time import TrueSolarConfig, to_true_solar_local


def test_true_solar_time_for_helsinki_gmt_plus_2_genesis_time():
    dt_utc = datetime(2009, 1, 3, 16, 15, 0, tzinfo=timezone.utc)
    config = TrueSolarConfig(enabled=True, longitude_deg=24.9384, tz_offset_hours=2.0)

    true_local = to_true_solar_local(dt_utc, config=config)

    assert true_local.hour == 17
    assert true_local.minute == 50


def test_btc_bazi_matches_true_solar_rule_gmt_plus_2_1815():
    dt_utc = datetime(2009, 1, 3, 16, 15, 0, tzinfo=timezone.utc)
    calendar = CalendarService(
        enable_crosscheck=True,
        enable_true_solar_time=True,
        solar_longitude_deg=24.9384,
        solar_tz_offset_hours=2.0,
        strict_calendar_lib=True,
    )

    snapshot = calendar.convert_utc(dt_utc)

    assert snapshot.year.text == "戊子"
    assert snapshot.month.text == "甲子"
    assert snapshot.day.text == "戊申"
    assert snapshot.hour.text == "辛酉"
