from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import BaziSnapshot, GanzhiPillar

from .base import CalendarProvider, CalendarProviderError, _fallback_snapshot
from .solar_time import TrueSolarConfig, format_true_solar_tag, to_true_solar_local


def _split_ganzhi(text: str) -> GanzhiPillar:
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        raise CalendarProviderError(f"invalid ganzhi text: {text!r}")
    return GanzhiPillar(stem=cleaned[0], branch=cleaned[1])


class LunarPythonProvider(CalendarProvider):
    def __init__(self, *, solar_config: TrueSolarConfig, strict_calendar_lib: bool = True) -> None:
        super().__init__(name="lunar-python")
        self._solar_config = solar_config
        self._strict_calendar_lib = bool(strict_calendar_lib)

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_utc = dt_utc.astimezone(timezone.utc)
        true_local = to_true_solar_local(dt_utc, config=self._solar_config)
        try:
            from lunar_python import Solar  # type: ignore

            solar = Solar.fromYmdHms(
                true_local.year,
                true_local.month,
                true_local.day,
                true_local.hour,
                true_local.minute,
                true_local.second,
            )
            lunar = solar.getLunar()
            return BaziSnapshot(
                source=f"{self.name}:{format_true_solar_tag(self._solar_config)}",
                dt_utc=dt_utc,
                year=_split_ganzhi(lunar.getYearInGanZhi()),
                month=_split_ganzhi(lunar.getMonthInGanZhi()),
                day=_split_ganzhi(lunar.getDayInGanZhi()),
                hour=_split_ganzhi(lunar.getTimeInGanZhi()),
            )
        except Exception as exc:
            if self._strict_calendar_lib:
                raise CalendarProviderError(f"{self.name} unavailable: {exc}") from exc
            return _fallback_snapshot(
                true_local,
                source=f"{self.name}:{format_true_solar_tag(self._solar_config)}:fallback",
            )
