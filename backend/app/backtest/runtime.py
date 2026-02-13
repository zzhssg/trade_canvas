from __future__ import annotations

from ..runtime.blocking import run_blocking
from ..freqtrade.runner import BacktestRunRequest, list_strategies, run_backtest


async def list_strategies_async(**kwargs):
    return await run_blocking(list_strategies, **kwargs)


async def run_backtest_async(**kwargs):
    request = kwargs.get("request")
    if isinstance(request, BacktestRunRequest):
        return await run_blocking(run_backtest, request=request)
    return await run_blocking(run_backtest, request=BacktestRunRequest(**kwargs))
