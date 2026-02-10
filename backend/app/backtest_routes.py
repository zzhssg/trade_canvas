from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query

from .dependencies import BacktestServiceDep
from .schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse

router = APIRouter()


@router.get("/api/backtest/strategies", response_model=StrategyListResponse)
async def get_backtest_strategies(
    recursive: bool = True,
    *,
    service: BacktestServiceDep,
) -> StrategyListResponse:
    return await service.get_strategies(recursive=recursive)


@router.get("/api/backtest/pair_timeframes", response_model=BacktestPairTimeframesResponse)
async def get_backtest_pair_timeframes(
    pair: str = Query(..., min_length=1),
    *,
    service: BacktestServiceDep,
) -> BacktestPairTimeframesResponse:
    return await service.get_pair_timeframes(pair=pair)


@router.post("/api/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_job(
    payload: BacktestRunRequest,
    *,
    service: BacktestServiceDep,
) -> BacktestRunResponse:
    return await service.run(payload=payload)


def register_backtest_routes(app: FastAPI) -> None:
    app.include_router(router)
