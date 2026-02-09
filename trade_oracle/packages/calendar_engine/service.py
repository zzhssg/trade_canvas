from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_oracle.models import BaziSnapshot

from .provider_lunar import LunarPythonProvider
from .provider_sxtwl import SxtwlProvider
from .solar_time import TrueSolarConfig


@dataclass(frozen=True)
class CalendarService:
    enable_crosscheck: bool = False
    enable_true_solar_time: bool = True
    solar_longitude_deg: float = 24.9384
    solar_tz_offset_hours: float = 2.0
    strict_calendar_lib: bool = True

    def __post_init__(self) -> None:
        solar_config = TrueSolarConfig(
            enabled=bool(self.enable_true_solar_time),
            longitude_deg=float(self.solar_longitude_deg),
            tz_offset_hours=float(self.solar_tz_offset_hours),
        )
        object.__setattr__(self, "_primary", LunarPythonProvider(solar_config=solar_config, strict_calendar_lib=self.strict_calendar_lib))
        object.__setattr__(self, "_secondary", SxtwlProvider(solar_config=solar_config, strict_calendar_lib=self.strict_calendar_lib))

    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        primary = self._primary.convert_utc(dt_utc)
        if not self.enable_crosscheck:
            return primary
        secondary = self._secondary.convert_utc(dt_utc)
        if self._same_bazi(primary, secondary):
            return primary
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
