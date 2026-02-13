from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ..backtest.service import BacktestService
from ..container import AppContainer
from ..worktree.manager import WorktreeManager
from .core import get_app_container


def get_backtest_service(container: AppContainer = Depends(get_app_container)) -> BacktestService:
    return container.backtest_service


def get_worktree_manager(container: AppContainer = Depends(get_app_container)) -> WorktreeManager:
    return container.worktree_manager


BacktestServiceDep = Annotated[BacktestService, Depends(get_backtest_service)]
WorktreeManagerDep = Annotated[WorktreeManager, Depends(get_worktree_manager)]
