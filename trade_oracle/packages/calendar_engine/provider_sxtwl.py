from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import BaziSnapshot, GanzhiPillar

from .base import CalendarProvider, CalendarProviderError, _fallback_snapshot
from .solar_time import TrueSolarConfig, format_true_solar_tag, to_true_solar_local

GAN = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
ZHI = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


def _pillar_from_indexes(tg: int, dz: int) -> GanzhiPillar:
    return GanzhiPillar(stem=GAN[int(tg) % 10], branch=ZHI[int(dz) % 12])


class SxtwlProvider(CalendarProvider):
    def __init__(self, *, solar_config: TrueSolarConfig, strict_calendar_lib: bool = True) -> None:
        super().__init__(name="sxtwl")
        self._solar_config = solar_config
        self._strict_calendar_lib = bool(strict_calendar_lib)

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_utc = dt_utc.astimezone(timezone.utc)
        true_local = to_true_solar_local(dt_utc, config=self._solar_config)
        try:
            import sxtwl  # type: ignore

            day = sxtwl.fromSolar(true_local.year, true_local.month, true_local.day)
            y = day.getYearGZ()
            m = day.getMonthGZ()
            d = day.getDayGZ()
            hour_branch = ((true_local.hour + 1) // 2) % 12
            hour_stem = (int(d.tg) * 2 + hour_branch) % 10
            return BaziSnapshot(
                source=f"{self.name}:{format_true_solar_tag(self._solar_config)}",
                dt_utc=dt_utc,
                year=_pillar_from_indexes(y.tg, y.dz),
                month=_pillar_from_indexes(m.tg, m.dz),
                day=_pillar_from_indexes(d.tg, d.dz),
                hour=_pillar_from_indexes(hour_stem, hour_branch),
            )
        except Exception as exc:
            if self._strict_calendar_lib:
                raise CalendarProviderError(f"{self.name} unavailable: {exc}") from exc
            return _fallback_snapshot(
                true_local,
                source=f"{self.name}:{format_true_solar_tag(self._solar_config)}:fallback",
            )
