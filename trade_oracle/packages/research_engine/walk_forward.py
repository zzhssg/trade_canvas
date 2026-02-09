from __future__ import annotations

from dataclasses import dataclass

from trade_oracle.models import Candle


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def build_daily_windows(candles: list[Candle], *, train_size: int = 360, test_size: int = 90) -> list[WalkForwardWindow]:
    windows: list[WalkForwardWindow] = []
    if len(candles) < train_size + test_size:
        return windows

    idx = 0
    while idx + train_size + test_size <= len(candles):
        train = candles[idx : idx + train_size]
        test = candles[idx + train_size : idx + train_size + test_size]
        windows.append(
            WalkForwardWindow(
                train_start_idx=idx,
                train_end_idx=idx + train_size - 1,
                test_start_idx=idx + train_size,
                test_end_idx=idx + train_size + test_size - 1,
                train_start=train[0].candle_time,
                train_end=train[-1].candle_time,
                test_start=test[0].candle_time,
                test_end=test[-1].candle_time,
            )
        )
        idx += test_size
    return windows
