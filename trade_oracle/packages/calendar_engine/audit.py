from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_oracle.models import BaziSnapshot

from .provider_lunar import LunarPythonProvider
from .provider_sxtwl import SxtwlProvider
from .solar_time import TrueSolarConfig


@dataclass(frozen=True)
class CalendarDiffEntry:
    ts_utc: str
    lunar: str
    sxtwl: str


@dataclass(frozen=True)
class CalendarCrosscheckReport:
    generated_at_utc: str
    samples: int
    mismatches: int
    mismatch_rate: float
    entries: list[CalendarDiffEntry]


def _snapshot_text(s: BaziSnapshot) -> str:
    return f"{s.year.text}-{s.month.text}-{s.day.text}-{s.hour.text}"


def build_sample_times(*, start_utc: datetime, end_utc: datetime, step_days: int = 7) -> list[datetime]:
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)
    start = start_utc.astimezone(timezone.utc)
    end = end_utc.astimezone(timezone.utc)
    if step_days <= 0:
        raise ValueError("step_days must be > 0")
    if end < start:
        raise ValueError("end_utc must be >= start_utc")

    cur = start
    out: list[datetime] = []
    while cur <= end:
        out.append(cur)
        cur = cur + timedelta(days=step_days)
    return out


def crosscheck_samples(
    *,
    sample_times: list[datetime],
    enable_true_solar_time: bool = True,
    solar_longitude_deg: float = 24.9384,
    solar_tz_offset_hours: float = 2.0,
    strict_calendar_lib: bool = True,
) -> CalendarCrosscheckReport:
    solar_config = TrueSolarConfig(
        enabled=bool(enable_true_solar_time),
        longitude_deg=float(solar_longitude_deg),
        tz_offset_hours=float(solar_tz_offset_hours),
    )
    lunar = LunarPythonProvider(solar_config=solar_config, strict_calendar_lib=strict_calendar_lib)
    sxtwl = SxtwlProvider(solar_config=solar_config, strict_calendar_lib=strict_calendar_lib)
    mismatches: list[CalendarDiffEntry] = []

    for ts in sample_times:
        a = lunar.convert_utc(ts)
        b = sxtwl.convert_utc(ts)
        a_txt = _snapshot_text(a)
        b_txt = _snapshot_text(b)
        if a_txt != b_txt:
            mismatches.append(
                CalendarDiffEntry(
                    ts_utc=ts.astimezone(timezone.utc).isoformat(),
                    lunar=a_txt,
                    sxtwl=b_txt,
                )
            )

    total = len(sample_times)
    mismatch_count = len(mismatches)
    rate = float(mismatch_count / total) if total > 0 else 0.0
    return CalendarCrosscheckReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        samples=total,
        mismatches=mismatch_count,
        mismatch_rate=rate,
        entries=mismatches,
    )


def write_report(*, report: CalendarCrosscheckReport, path: Path) -> None:
    payload = {
        "generated_at_utc": report.generated_at_utc,
        "samples": report.samples,
        "mismatches": report.mismatches,
        "mismatch_rate": report.mismatch_rate,
        "entries": [
            {
                "ts_utc": e.ts_utc,
                "lunar": e.lunar,
                "sxtwl": e.sxtwl,
            }
            for e in report.entries
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
