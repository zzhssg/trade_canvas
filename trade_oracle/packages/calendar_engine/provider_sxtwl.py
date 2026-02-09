from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import BaziSnapshot, GanzhiPillar

from .base import CalendarProvider, _fallback_snapshot

GAN = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
ZHI = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


def _pillar_from_indexes(tg: int, dz: int) -> GanzhiPillar:
    return GanzhiPillar(stem=GAN[int(tg) % 10], branch=ZHI[int(dz) % 12])


class SxtwlProvider(CalendarProvider):
    def __init__(self) -> None:
        super().__init__(name="sxtwl")

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_utc = dt_utc.astimezone(timezone.utc)
        try:
            import sxtwl  # type: ignore

            day = sxtwl.fromSolar(dt_utc.year, dt_utc.month, dt_utc.day)
            y = day.getYearGZ()
            m = day.getMonthGZ()
            d = day.getDayGZ()
            hour_branch = ((dt_utc.hour + 1) // 2) % 12
            hour_stem = (int(d.tg) * 2 + hour_branch) % 10
            return BaziSnapshot(
                source=self.name,
                dt_utc=dt_utc,
                year=_pillar_from_indexes(y.tg, y.dz),
                month=_pillar_from_indexes(m.tg, m.dz),
                day=_pillar_from_indexes(d.tg, d.dz),
                hour=_pillar_from_indexes(hour_stem, hour_branch),
            )
        except Exception:
            return _fallback_snapshot(dt_utc, source=f"{self.name}:fallback")
