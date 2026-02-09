from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import BaziSnapshot, GanzhiPillar

from .base import CalendarProvider, CalendarProviderError, _fallback_snapshot


def _split_ganzhi(text: str) -> GanzhiPillar:
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        raise CalendarProviderError(f"invalid ganzhi text: {text!r}")
    return GanzhiPillar(stem=cleaned[0], branch=cleaned[1])


class LunarPythonProvider(CalendarProvider):
    def __init__(self) -> None:
        super().__init__(name="lunar-python")

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_utc = dt_utc.astimezone(timezone.utc)
        try:
            from lunar_python import Solar  # type: ignore

            solar = Solar.fromYmdHms(
                dt_utc.year,
                dt_utc.month,
                dt_utc.day,
                dt_utc.hour,
                dt_utc.minute,
                dt_utc.second,
            )
            lunar = solar.getLunar()
            return BaziSnapshot(
                source=self.name,
                dt_utc=dt_utc,
                year=_split_ganzhi(lunar.getYearInGanZhi()),
                month=_split_ganzhi(lunar.getMonthInGanZhi()),
                day=_split_ganzhi(lunar.getDayInGanZhi()),
                hour=_split_ganzhi(lunar.getTimeInGanZhi()),
            )
        except Exception:
            return _fallback_snapshot(dt_utc, source=f"{self.name}:fallback")
