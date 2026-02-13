from __future__ import annotations

from dataclasses import dataclass

from ..backtest.service import BacktestService
from ..core.config import Settings
from ..debug.hub import DebugHub
from ..factor.orchestrator import FactorOrchestrator
from ..factor.slices_service import FactorSlicesService
from ..factor.store import FactorStore
from ..ledger.sync_service import LedgerSyncService
from ..lifecycle.service import AppLifecycleService
from ..market.runtime import MarketRuntime
from ..overlay.orchestrator import OverlayOrchestrator
from ..overlay.package_service_v1 import OverlayReplayPackageServiceV1
from ..overlay.store import OverlayStore
from ..read_models import DrawReadService, FactorReadService, ReadRepairService, WorldReadService
from ..replay.package_service_v1 import ReplayPackageServiceV1
from ..replay.prepare_service import ReplayPrepareService
from ..runtime.api_gates import ApiGateConfig
from ..runtime.flags import RuntimeFlags
from ..runtime.metrics import RuntimeMetrics
from ..storage.candle_store import CandleStore
from ..worktree.manager import WorktreeManager


@dataclass(frozen=True)
class CoreContainerContext:
    settings: Settings
    runtime_flags: RuntimeFlags
    api_gates: ApiGateConfig
    debug_hub: DebugHub
    runtime_metrics: RuntimeMetrics
    worktree_manager: WorktreeManager


@dataclass(frozen=True)
class StoreContainerContext:
    store: CandleStore
    factor_store: FactorStore
    overlay_store: OverlayStore


@dataclass(frozen=True)
class FactorContainerContext:
    factor_orchestrator: FactorOrchestrator
    factor_slices_service: FactorSlicesService
    factor_read_service: FactorReadService
    ledger_sync_service: LedgerSyncService
    overlay_orchestrator: OverlayOrchestrator


@dataclass(frozen=True)
class ReadContainerContext:
    draw_read_service: DrawReadService
    world_read_service: WorldReadService
    read_repair_service: ReadRepairService


@dataclass(frozen=True)
class ReplayContainerContext:
    replay_prepare_service: ReplayPrepareService
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1


@dataclass(frozen=True)
class MarketContainerContext:
    market_runtime: MarketRuntime
    lifecycle: AppLifecycleService


@dataclass(frozen=True)
class DevContainerContext:
    backtest_service: BacktestService
