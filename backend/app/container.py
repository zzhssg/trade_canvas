from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .backtest_runtime import list_strategies_async, run_backtest_async
from .backtest_service import BacktestService
from .config import Settings
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .factor_runtime_config import FactorSettings
from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .flags import FeatureFlags, load_feature_flags
from .ingest_supervisor import IngestSupervisor
from .market_runtime import MarketRuntime
from .market_runtime_builder import build_market_runtime
from .overlay_orchestrator import OverlayOrchestrator, OverlaySettings
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .read_models import DrawReadService, FactorReadService, WorldReadService
from .replay_prepare_service import ReplayPrepareService
from .replay_package_service_v1 import ReplayPackageServiceV1
from .runtime_flags import RuntimeFlags, load_runtime_flags
from .store import CandleStore
from .worktree_manager import WorktreeManager
from .ws_hub import CandleHub


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
    overlay_store: OverlayStore
    overlay_orchestrator: OverlayOrchestrator
    replay_prepare_service: ReplayPrepareService
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1
    backtest_service: BacktestService
    debug_hub: DebugHub
    hub: CandleHub
    ingest_pipeline: IngestPipeline
    market_runtime: MarketRuntime
    supervisor: IngestSupervisor
    worktree_manager: WorktreeManager
    whitelist_ingest_enabled: bool


def build_app_container(*, settings: Settings, project_root: Path) -> AppContainer:
    flags = load_feature_flags()
    runtime_flags = load_runtime_flags(base_flags=flags)

    store = CandleStore(db_path=settings.db_path)
    factor_store = FactorStore(db_path=settings.db_path)
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

    overlay_store = OverlayStore(db_path=settings.db_path)
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
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        strict_mode=bool(flags.enable_read_strict_mode),
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
        flags=flags,
        runtime_flags=runtime_flags,
    )

    ingest_pipeline = runtime_build.runtime.ingest_pipeline

    replay_prepare_service = ReplayPrepareService(
        store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        ingest_pipeline=ingest_pipeline,
        debug_hub=debug_hub,
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
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        replay_prepare_service=replay_prepare_service,
        replay_service=replay_service,
        overlay_pkg_service=overlay_pkg_service,
        backtest_service=backtest_service,
        debug_hub=debug_hub,
        hub=runtime_build.hub,
        ingest_pipeline=ingest_pipeline,
        market_runtime=runtime_build.runtime,
        supervisor=runtime_build.supervisor,
        worktree_manager=worktree_manager,
        whitelist_ingest_enabled=runtime_build.whitelist_ingest_on,
    )
