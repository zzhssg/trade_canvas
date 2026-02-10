from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .backtest_service import BacktestService
from .config import Settings
from .container import AppContainer
from .debug_hub import DebugHub
from .factor_store import FactorStore
from .flags import FeatureFlags
from .market_runtime import MarketRuntime
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .overlay_store import OverlayStore
from .read_models import DrawReadService, FactorReadService, WorldReadService
from .replay_prepare_service import ReplayPrepareService
from .replay_package_service_v1 import ReplayPackageServiceV1
from .store import CandleStore
from .worktree_manager import WorktreeManager


def get_app_container(request: Request) -> AppContainer:
    container = getattr(request.app.state, "container", None)
    if isinstance(container, AppContainer):
        return container
    raise HTTPException(status_code=500, detail="container_not_ready")


def get_settings(container: AppContainer = Depends(get_app_container)) -> Settings:
    return container.settings


def get_feature_flags(container: AppContainer = Depends(get_app_container)) -> FeatureFlags:
    return container.flags


def get_market_runtime(container: AppContainer = Depends(get_app_container)) -> MarketRuntime:
    return container.market_runtime


def get_candle_store(container: AppContainer = Depends(get_app_container)) -> CandleStore:
    return container.store


def get_factor_store(container: AppContainer = Depends(get_app_container)) -> FactorStore:
    return container.factor_store


def get_overlay_store(container: AppContainer = Depends(get_app_container)) -> OverlayStore:
    return container.overlay_store


def get_factor_read_service(container: AppContainer = Depends(get_app_container)) -> FactorReadService:
    return container.factor_read_service


def get_draw_read_service(container: AppContainer = Depends(get_app_container)) -> DrawReadService:
    return container.draw_read_service


def get_world_read_service(container: AppContainer = Depends(get_app_container)) -> WorldReadService:
    return container.world_read_service


def get_debug_hub(container: AppContainer = Depends(get_app_container)) -> DebugHub:
    return container.debug_hub


def get_replay_service(container: AppContainer = Depends(get_app_container)) -> ReplayPackageServiceV1:
    return container.replay_service


def get_replay_prepare_service(container: AppContainer = Depends(get_app_container)) -> ReplayPrepareService:
    return container.replay_prepare_service


def get_overlay_package_service(
    container: AppContainer = Depends(get_app_container),
) -> OverlayReplayPackageServiceV1:
    return container.overlay_pkg_service


def get_backtest_service(container: AppContainer = Depends(get_app_container)) -> BacktestService:
    return container.backtest_service


def get_worktree_manager(container: AppContainer = Depends(get_app_container)) -> WorktreeManager:
    return container.worktree_manager


AppContainerDep = Annotated[AppContainer, Depends(get_app_container)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
FeatureFlagsDep = Annotated[FeatureFlags, Depends(get_feature_flags)]
MarketRuntimeDep = Annotated[MarketRuntime, Depends(get_market_runtime)]
CandleStoreDep = Annotated[CandleStore, Depends(get_candle_store)]
FactorStoreDep = Annotated[FactorStore, Depends(get_factor_store)]
OverlayStoreDep = Annotated[OverlayStore, Depends(get_overlay_store)]
FactorReadServiceDep = Annotated[FactorReadService, Depends(get_factor_read_service)]
DrawReadServiceDep = Annotated[DrawReadService, Depends(get_draw_read_service)]
WorldReadServiceDep = Annotated[WorldReadService, Depends(get_world_read_service)]
DebugHubDep = Annotated[DebugHub, Depends(get_debug_hub)]
ReplayServiceDep = Annotated[ReplayPackageServiceV1, Depends(get_replay_service)]
ReplayPrepareServiceDep = Annotated[ReplayPrepareService, Depends(get_replay_prepare_service)]
OverlayPackageServiceDep = Annotated[OverlayReplayPackageServiceV1, Depends(get_overlay_package_service)]
BacktestServiceDep = Annotated[BacktestService, Depends(get_backtest_service)]
WorktreeManagerDep = Annotated[WorktreeManager, Depends(get_worktree_manager)]
