from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_oracle.models import BaziSnapshot

from .provider_lunar import LunarPythonProvider
from .provider_sxtwl import SxtwlProvider


@dataclass(frozen=True)
class CalendarService:
    enable_crosscheck: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "_primary", LunarPythonProvider())
        object.__setattr__(self, "_secondary", SxtwlProvider())

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        primary = self._primary.convert_utc(dt_utc)
        if not self.enable_crosscheck:
            return primary
        secondary = self._secondary.convert_utc(dt_utc)
        if self._same_bazi(primary, secondary):
            return primary
        # 当结果不一致时保留主引擎，同时在 source 标注冲突。
        return BaziSnapshot(
            source=f"{primary.source}|crosscheck_mismatch:{secondary.source}",
            dt_utc=primary.dt_utc,
            year=primary.year,
            month=primary.month,
            day=primary.day,
            hour=primary.hour,
        )

    @staticmethod
    def _same_bazi(a: BaziSnapshot, b: BaziSnapshot) -> bool:
        return (
            a.year.text == b.year.text
            and a.month.text == b.month.text
            and a.day.text == b.day.text
            and a.hour.text == b.hour.text
        )
