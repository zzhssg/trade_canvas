from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trade_oracle.models import BaziSnapshot, GanzhiPillar
from trade_oracle.packages.research_engine.backtest import run_layer_segment_backtest, run_walk_forward_backtest


class _FakeCalendar:
    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        return BaziSnapshot(
            source="fake",
            dt_utc=dt_utc.astimezone(timezone.utc),
            year=GanzhiPillar("甲", "子"),
            month=GanzhiPillar("乙", "丑"),
            day=GanzhiPillar("甲", "寅"),
            hour=GanzhiPillar("丙", "卯"),
        )


def test_run_walk_forward_backtest_has_metrics():
    rows = json.loads(Path("trade_oracle/fixtures/btc_1d_mock_120.json").read_text(encoding="utf-8"))

    class CandleObj:
        def __init__(self, row: dict):
            self.candle_time = row["candle_time"]
            self.open = row["open"]
            self.high = row["high"]
            self.low = row["low"]
            self.close = row["close"]
            self.volume = row["volume"]

    candles = [CandleObj(r) for r in rows]
    natal = BaziSnapshot(
        source="fake",
        dt_utc=datetime(2009, 1, 3, 18, 15, 5, tzinfo=timezone.utc),
        year=GanzhiPillar("甲", "子"),
        month=GanzhiPillar("乙", "丑"),
        day=GanzhiPillar("丙", "寅"),
        hour=GanzhiPillar("丁", "卯"),
    )

    result = run_walk_forward_backtest(
        candles=candles,
        natal=natal,
        calendar=_FakeCalendar(),
        train_size=60,
        test_size=20,
    )

    assert result.windows >= 1
    assert result.threshold is not None
    assert result.trades >= 0


def test_run_layer_segment_backtest_has_segments_and_layers():
    rows = json.loads(Path("trade_oracle/fixtures/btc_1d_mock_120.json").read_text(encoding="utf-8"))

    class CandleObj:
        def __init__(self, row: dict):
            self.candle_time = row["candle_time"]
            self.open = row["open"]
            self.high = row["high"]
            self.low = row["low"]
            self.close = row["close"]
            self.volume = row["volume"]

    candles = [CandleObj(r) for r in rows]
    natal = BaziSnapshot(
        source="fake",
        dt_utc=datetime(2009, 1, 3, 16, 15, 0, tzinfo=timezone.utc),
        year=GanzhiPillar("戊", "子"),
        month=GanzhiPillar("甲", "子"),
        day=GanzhiPillar("戊", "申"),
        hour=GanzhiPillar("辛", "酉"),
    )

    result = run_layer_segment_backtest(candles=candles, natal=natal, calendar=_FakeCalendar())

    assert set(result["layer_performance"].keys()) == {"year", "month", "day"}
    assert len(result["time_segments"]) == 3
    assert all("strategy" in seg for seg in result["time_segments"])
