from __future__ import annotations

from trade_oracle.models import Candle
from trade_oracle.packages.research_engine.walk_forward import build_daily_windows


def test_build_daily_windows():
    candles = [
        Candle(candle_time=1700000000 + i * 86400, open=1, high=1, low=1, close=1 + i * 0.01, volume=1)
        for i in range(540)
    ]

    windows = build_daily_windows(candles, train_size=360, test_size=90)
    assert len(windows) == 2
    assert windows[0].train_start_idx == 0
    assert windows[0].test_start_idx == 360
    assert windows[0].train_start == candles[0].candle_time
    assert windows[0].test_start == candles[360].candle_time
    assert windows[1].test_end_idx == 539
    assert windows[1].test_end == candles[539].candle_time
