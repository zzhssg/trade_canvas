from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trade_oracle.packages.calendar_engine.audit import build_sample_times, crosscheck_samples, write_report


def test_build_sample_times_over_100():
    start = datetime(2009, 1, 3, 18, 15, 5, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    samples = build_sample_times(start_utc=start, end_utc=end, step_days=30)
    assert len(samples) > 100


def test_crosscheck_report_write(tmp_path: Path):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 1, tzinfo=timezone.utc)
    samples = build_sample_times(start_utc=start, end_utc=end, step_days=15)
    report = crosscheck_samples(sample_times=samples)
    output = tmp_path / "calendar_report.json"
    write_report(report=report, path=output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["samples"] == len(samples)
    assert "mismatch_rate" in payload
    assert isinstance(payload["entries"], list)
