from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class TrueSolarConfig:
    enabled: bool = True
    longitude_deg: float = 24.9384
    tz_offset_hours: float = 2.0


def _equation_of_time_minutes(day_of_year: int) -> float:
    # Approximation (minutes): EoT = 9.87 sin(2B) - 7.53 cos(B) - 1.5 sin(B)
    b = 2.0 * math.pi * (float(day_of_year) - 81.0) / 364.0
    return 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def _time_correction_minutes(*, longitude_deg: float, tz_offset_hours: float, day_of_year: int) -> float:
    local_standard_meridian = 15.0 * float(tz_offset_hours)
    longitude_term = 4.0 * (float(longitude_deg) - local_standard_meridian)
    return longitude_term + _equation_of_time_minutes(day_of_year)


def to_true_solar_local(dt_utc: datetime, *, config: TrueSolarConfig) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)

    if not config.enabled:
        return dt_utc

    local_standard = dt_utc + timedelta(hours=float(config.tz_offset_hours))
    day_of_year = int(local_standard.timetuple().tm_yday)
    correction_minutes = _time_correction_minutes(
        longitude_deg=float(config.longitude_deg),
        tz_offset_hours=float(config.tz_offset_hours),
        day_of_year=day_of_year,
    )
    return local_standard + timedelta(minutes=correction_minutes)


def format_true_solar_tag(config: TrueSolarConfig) -> str:
    mode = "on" if config.enabled else "off"
    return f"true_solar:{mode}:lon={config.longitude_deg:.4f}:tz={config.tz_offset_hours:.2f}"
