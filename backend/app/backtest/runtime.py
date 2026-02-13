from __future__ import annotations

from ..blocking import run_blocking
from ..freqtrade.runner import list_strategies, run_backtest


async def list_strategies_async(**kwargs):
    return await run_blocking(list_strategies, **kwargs)


async def run_backtest_async(**kwargs):
    return await run_blocking(run_backtest, **kwargs)
