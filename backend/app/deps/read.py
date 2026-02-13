from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ..container import AppContainer
from ..debug.hub import DebugHub
from ..factor.store import FactorStore
from ..overlay.store import OverlayStore
from ..read_models import DrawReadService, FactorReadService, ReadRepairService, WorldReadService
from ..runtime.metrics import RuntimeMetrics
from ..store import CandleStore
from .core import get_app_container


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


def get_read_repair_service(container: AppContainer = Depends(get_app_container)) -> ReadRepairService:
    return container.read_repair_service


def get_debug_hub(container: AppContainer = Depends(get_app_container)) -> DebugHub:
    return container.debug_hub


def get_runtime_metrics(container: AppContainer = Depends(get_app_container)) -> RuntimeMetrics:
    return container.runtime_metrics


CandleStoreDep = Annotated[CandleStore, Depends(get_candle_store)]
FactorStoreDep = Annotated[FactorStore, Depends(get_factor_store)]
OverlayStoreDep = Annotated[OverlayStore, Depends(get_overlay_store)]
FactorReadServiceDep = Annotated[FactorReadService, Depends(get_factor_read_service)]
DrawReadServiceDep = Annotated[DrawReadService, Depends(get_draw_read_service)]
WorldReadServiceDep = Annotated[WorldReadService, Depends(get_world_read_service)]
ReadRepairServiceDep = Annotated[ReadRepairService, Depends(get_read_repair_service)]
DebugHubDep = Annotated[DebugHub, Depends(get_debug_hub)]
RuntimeMetricsDep = Annotated[RuntimeMetrics, Depends(get_runtime_metrics)]
