from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query

from ..deps import BacktestServiceDep
from ..core.schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse
from ..core.service_errors import ServiceError, to_http_exception

router = APIRouter()


@router.get("/api/backtest/strategies", response_model=StrategyListResponse)
async def get_backtest_strategies(
    recursive: bool = True,
    *,
    service: BacktestServiceDep,
) -> StrategyListResponse:
    try:
        return await service.get_strategies(recursive=recursive)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/backtest/pair_timeframes", response_model=BacktestPairTimeframesResponse)
async def get_backtest_pair_timeframes(
    pair: str = Query(..., min_length=1),
    *,
    service: BacktestServiceDep,
) -> BacktestPairTimeframesResponse:
    try:
        return await service.get_pair_timeframes(pair=pair)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_job(
    payload: BacktestRunRequest,
    *,
    service: BacktestServiceDep,
) -> BacktestRunResponse:
    try:
        return await service.run(payload=payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_backtest_routes(app: FastAPI) -> None:
    app.include_router(router)
