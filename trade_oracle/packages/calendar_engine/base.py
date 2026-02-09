from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from trade_oracle.models import BaziSnapshot, GanzhiPillar


class CalendarProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalendarProvider:
    name: str

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        raise NotImplementedError


GAN: tuple[str, ...] = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
ZHI: tuple[str, ...] = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


def _fallback_snapshot(dt_utc: datetime, *, source: str) -> BaziSnapshot:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    ts = int(dt_utc.timestamp())

    def pillar(offset: int) -> GanzhiPillar:
        idx = abs((ts // 3600 + offset) % 60)
        return GanzhiPillar(stem=GAN[idx % 10], branch=ZHI[idx % 12])

    return BaziSnapshot(
        source=source,
        dt_utc=dt_utc.astimezone(timezone.utc),
        year=pillar(0),
        month=pillar(7),
        day=pillar(19),
        hour=pillar(31),
    )
