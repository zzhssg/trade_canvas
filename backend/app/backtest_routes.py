from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .backtest_service import BacktestService
from .blocking import run_blocking
from .flags import resolve_env_bool
from .freqtrade_runner import list_strategies, run_backtest
from .schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse

router = APIRouter()
logger = logging.getLogger(__name__)


async def list_strategies_async(**kwargs):
    return await run_blocking(list_strategies, **kwargs)


async def run_backtest_async(**kwargs):
    return await run_blocking(run_backtest, **kwargs)


def _require_backtest_trades() -> bool:
    return resolve_env_bool("TRADE_CANVAS_BACKTEST_REQUIRE_TRADES", fallback=False)


def _freqtrade_mock_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_FREQTRADE_MOCK", fallback=False)


def _settings(request: Request):
    settings = request.app.state.settings
    if settings is None:
        raise HTTPException(status_code=500, detail="settings_not_ready")
    return settings


def _project_root(request: Request) -> Path:
    project_root = request.app.state.project_root
    if not isinstance(project_root, Path):
        raise HTTPException(status_code=500, detail="project_root_not_ready")
    return project_root


def _backtest_service(request: Request) -> BacktestService:
    service = getattr(request.app.state, "backtest_service", None)
    if service is not None:
        return service

    service = BacktestService(
        settings=_settings(request),
        project_root=_project_root(request),
        list_strategies=list_strategies_async,
        run_backtest=run_backtest_async,
        require_backtest_trades=_require_backtest_trades,
        freqtrade_mock_enabled=_freqtrade_mock_enabled,
        logger=logger,
    )
    request.app.state.backtest_service = service
    return service


@router.get("/api/backtest/strategies", response_model=StrategyListResponse)
async def get_backtest_strategies(request: Request, recursive: bool = True) -> StrategyListResponse:
    return await _backtest_service(request).get_strategies(recursive=recursive)


@router.get("/api/backtest/pair_timeframes", response_model=BacktestPairTimeframesResponse)
async def get_backtest_pair_timeframes(request: Request, pair: str = Query(..., min_length=1)) -> BacktestPairTimeframesResponse:
    return await _backtest_service(request).get_pair_timeframes(pair=pair)


@router.post("/api/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_job(request: Request, payload: BacktestRunRequest) -> BacktestRunResponse:
    return await _backtest_service(request).run(payload=payload)


def register_backtest_routes(app: FastAPI) -> None:
    app.include_router(router)
