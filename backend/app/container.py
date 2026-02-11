from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .app_lifecycle_service import AppLifecycleService
from .backtest_runtime import list_strategies_async, run_backtest_async
from .backtest_service import BacktestService
from .blocking import configure_blocking_executor
from .config import Settings
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .factor_runtime_config import FactorSettings
from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .flags import FeatureFlags, load_feature_flags
from .ledger_sync_service import LedgerSyncService
from .market_runtime import MarketRuntime
from .market_runtime_builder import build_market_runtime
from .overlay_orchestrator import OverlayOrchestrator, OverlaySettings
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .read_models import DrawReadService, FactorReadService, ReadRepairService, WorldReadService
from .replay_prepare_service import ReplayPrepareService
from .replay_package_service_v1 import ReplayPackageServiceV1
from .runtime_flags import RuntimeFlags, load_runtime_flags
from .runtime_metrics import RuntimeMetrics
from .store import CandleStore
from .worktree_manager import WorktreeManager


@dataclass(frozen=True)
class AppContainer:
    project_root: Path
    settings: Settings
    flags: FeatureFlags
    runtime_flags: RuntimeFlags
    store: CandleStore
    factor_store: FactorStore
    factor_orchestrator: FactorOrchestrator
    factor_slices_service: FactorSlicesService
    factor_read_service: FactorReadService
    draw_read_service: DrawReadService
    world_read_service: WorldReadService
    read_repair_service: ReadRepairService
    ledger_sync_service: LedgerSyncService
    overlay_store: OverlayStore
    overlay_orchestrator: OverlayOrchestrator
    replay_prepare_service: ReplayPrepareService
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1
    backtest_service: BacktestService
    debug_hub: DebugHub
    runtime_metrics: RuntimeMetrics
    market_runtime: MarketRuntime
    lifecycle: AppLifecycleService
    worktree_manager: WorktreeManager


def build_app_container(*, settings: Settings, project_root: Path) -> AppContainer:
    flags = load_feature_flags()
    runtime_flags = load_runtime_flags(base_flags=flags)
    configure_blocking_executor(workers=int(runtime_flags.blocking_workers))
    runtime_metrics = RuntimeMetrics(enabled=bool(runtime_flags.enable_runtime_metrics))

    store = CandleStore(
        db_path=settings.db_path,
    )
    factor_store = FactorStore(
        db_path=settings.db_path,
    )
    factor_orchestrator = FactorOrchestrator(
        candle_store=store,
        factor_store=factor_store,
        settings=FactorSettings(
            pivot_window_major=int(runtime_flags.factor_pivot_window_major),
            pivot_window_minor=int(runtime_flags.factor_pivot_window_minor),
            lookback_candles=int(runtime_flags.factor_lookback_candles),
            state_rebuild_event_limit=int(runtime_flags.factor_state_rebuild_event_limit),
        ),
        ingest_enabled=bool(runtime_flags.enable_factor_ingest),
        fingerprint_rebuild_enabled=bool(runtime_flags.enable_factor_fingerprint_rebuild),
        factor_rebuild_keep_candles=int(runtime_flags.factor_rebuild_keep_candles),
        logic_version_override=str(runtime_flags.factor_logic_version_override or ""),
    )
    factor_slices_service = FactorSlicesService(candle_store=store, factor_store=factor_store)

    overlay_store = OverlayStore(
        db_path=settings.db_path,
    )
    overlay_orchestrator = OverlayOrchestrator(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        settings=OverlaySettings(
            ingest_enabled=bool(runtime_flags.enable_overlay_ingest),
            window_candles=int(runtime_flags.overlay_window_candles),
        ),
    )

    debug_hub = DebugHub()
    factor_orchestrator.set_debug_hub(debug_hub)
    overlay_orchestrator.set_debug_hub(debug_hub)

    factor_read_service = FactorReadService(
        store=store,
        factor_store=factor_store,
        factor_slices_service=factor_slices_service,
        strict_mode=True,
    )
    draw_read_service = DrawReadService(
        store=store,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        factor_read_service=factor_read_service,
        debug_hub=debug_hub,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )
    world_read_service = WorldReadService(
        store=store,
        overlay_store=overlay_store,
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        debug_hub=debug_hub,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )

    runtime_build = build_market_runtime(
        settings=settings,
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        runtime_metrics=runtime_metrics,
        flags=flags,
        runtime_flags=runtime_flags,
    )
    lifecycle = AppLifecycleService(
        market_runtime=runtime_build.runtime,
    )

    ingest_pipeline = runtime_build.runtime.ingest_ctx.ingest_pipeline
    ledger_sync_service = runtime_build.ledger_sync_service
    read_repair_service = ReadRepairService(
        store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        ingest_pipeline=ingest_pipeline,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        ledger_sync_service=ledger_sync_service,
        enable_ledger_sync_service=bool(runtime_flags.enable_ledger_sync_service),
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )

    replay_prepare_service = ReplayPrepareService(
        store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        ingest_pipeline=ingest_pipeline,
        debug_hub=debug_hub,
        ledger_sync_service=ledger_sync_service,
        enable_ledger_sync_service=bool(runtime_flags.enable_ledger_sync_service),
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )
    replay_service = ReplayPackageServiceV1(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        factor_slices_service=factor_slices_service,
        ingest_pipeline=ingest_pipeline,
        replay_enabled=bool(runtime_flags.enable_replay_v1),
        coverage_enabled=bool(runtime_flags.enable_replay_ensure_coverage),
        ccxt_backfill_enabled=bool(runtime_flags.enable_ccxt_backfill),
        market_history_source=str(runtime_flags.market_history_source),
    )
    overlay_pkg_service = OverlayReplayPackageServiceV1(
        candle_store=store,
        overlay_store=overlay_store,
        replay_package_enabled=bool(runtime_flags.enable_replay_package),
    )
    backtest_service = BacktestService(
        settings=settings,
        project_root=project_root,
        list_strategies=list_strategies_async,
        run_backtest=run_backtest_async,
        require_backtest_trades=bool(runtime_flags.backtest_require_trades),
        freqtrade_mock_enabled=bool(runtime_flags.freqtrade_mock_enabled),
    )

    worktree_manager = WorktreeManager(repo_root=project_root)

    return AppContainer(
        project_root=project_root,
        settings=settings,
        flags=flags,
        runtime_flags=runtime_flags,
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        world_read_service=world_read_service,
        read_repair_service=read_repair_service,
        ledger_sync_service=ledger_sync_service,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        replay_prepare_service=replay_prepare_service,
        replay_service=replay_service,
        overlay_pkg_service=overlay_pkg_service,
        backtest_service=backtest_service,
        debug_hub=debug_hub,
        runtime_metrics=runtime_metrics,
        market_runtime=runtime_build.runtime,
        lifecycle=lifecycle,
        worktree_manager=worktree_manager,
    )
