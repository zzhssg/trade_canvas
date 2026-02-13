from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .backtest.runtime import list_strategies_async, run_backtest_async
from .backtest.service import BacktestService
from .config import Settings
from .debug.hub import DebugHub
from .factor.orchestrator import FactorOrchestrator
from .factor.runtime_config import FactorSettings
from .factor.slices_service import FactorSlicesService
from .factor.store import FactorStore
from .ledger.sync_service import LedgerSyncService
from .overlay.orchestrator import OverlayOrchestrator, OverlaySettings
from .overlay.package_service_v1 import OverlayReplayPackageServiceV1
from .overlay.store import OverlayStore
from .pipelines import IngestPipeline
from .read_models import DrawReadService, FactorReadService, ReadRepairService, WorldReadService
from .replay.prepare_service import ReplayPrepareService
from .replay.package_service_v1 import ReplayPackageServiceV1
from .runtime.flags import RuntimeFlags
from .store import CandleStore
from .storage import PostgresCandleRepository, PostgresFactorRepository, PostgresOverlayRepository, PostgresPool


@dataclass(frozen=True)
class DomainCore:
    store: CandleStore
    factor_store: FactorStore
    factor_orchestrator: FactorOrchestrator
    factor_slices_service: FactorSlicesService
    overlay_store: OverlayStore
    overlay_orchestrator: OverlayOrchestrator
    debug_hub: DebugHub


@dataclass(frozen=True)
class ReadCoreServices:
    factor_read_service: FactorReadService
    draw_read_service: DrawReadService
    world_read_service: WorldReadService


@dataclass(frozen=True)
class ReplayServices:
    replay_prepare_service: ReplayPrepareService
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1


def _build_candle_store(
    *,
    settings: Settings,
    postgres_pool: PostgresPool | None,
) -> CandleStore:
    if postgres_pool is not None:
        return cast(
            CandleStore,
            PostgresCandleRepository(
                pool=postgres_pool,
                schema=settings.postgres_schema,
            ),
        )
    return CandleStore(db_path=settings.db_path)


def build_domain_core(*, settings: Settings, runtime_flags: RuntimeFlags, postgres_pool: PostgresPool | None) -> DomainCore:
    store = _build_candle_store(
        settings=settings,
        postgres_pool=postgres_pool,
    )
    factor_store: FactorStore
    if postgres_pool is not None:
        factor_store = PostgresFactorRepository(
            pool=postgres_pool,
            schema=settings.postgres_schema,
        )
    else:
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

    overlay_store: OverlayStore
    if postgres_pool is not None:
        overlay_store = PostgresOverlayRepository(
            pool=postgres_pool,
            schema=settings.postgres_schema,
        )
    else:
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

    return DomainCore(
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
    )


def build_read_core_services(*, core: DomainCore, runtime_flags: RuntimeFlags) -> ReadCoreServices:
    factor_read_service = FactorReadService(
        store=core.store,
        factor_store=core.factor_store,
        factor_slices_service=core.factor_slices_service,
        strict_mode=True,
    )
    draw_read_service = DrawReadService(
        store=core.store,
        overlay_store=core.overlay_store,
        overlay_orchestrator=core.overlay_orchestrator,
        factor_read_service=factor_read_service,
        debug_hub=core.debug_hub,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )
    world_read_service = WorldReadService(
        store=core.store,
        overlay_store=core.overlay_store,
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        debug_hub=core.debug_hub,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )
    return ReadCoreServices(
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        world_read_service=world_read_service,
    )


def build_read_repair_service(
    *,
    core: DomainCore,
    runtime_flags: RuntimeFlags,
    ledger_sync_service: LedgerSyncService,
) -> ReadRepairService:
    return ReadRepairService(
        overlay_orchestrator=core.overlay_orchestrator,
        debug_hub=core.debug_hub,
        ledger_sync_service=ledger_sync_service,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )


def build_replay_services(
    *,
    core: DomainCore,
    runtime_flags: RuntimeFlags,
    ingest_pipeline: IngestPipeline,
    ledger_sync_service: LedgerSyncService,
) -> ReplayServices:
    replay_prepare_service = ReplayPrepareService(
        ledger_sync_service=ledger_sync_service,
        debug_hub=core.debug_hub,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
    )
    replay_service = ReplayPackageServiceV1(
        candle_store=core.store,
        factor_store=core.factor_store,
        overlay_store=core.overlay_store,
        factor_slices_service=core.factor_slices_service,
        ingest_pipeline=ingest_pipeline,
        replay_enabled=bool(runtime_flags.enable_replay_v1),
        coverage_enabled=bool(runtime_flags.enable_replay_ensure_coverage),
        ccxt_backfill_enabled=bool(runtime_flags.enable_ccxt_backfill),
        market_history_source=str(runtime_flags.market_history_source),
    )
    overlay_pkg_service = OverlayReplayPackageServiceV1(
        candle_store=core.store,
        overlay_store=core.overlay_store,
        replay_package_enabled=bool(runtime_flags.enable_replay_package),
    )
    return ReplayServices(
        replay_prepare_service=replay_prepare_service,
        replay_service=replay_service,
        overlay_pkg_service=overlay_pkg_service,
    )


def build_backtest_service(*, settings: Settings, project_root: Path, runtime_flags: RuntimeFlags) -> BacktestService:
    return BacktestService(
        settings=settings,
        project_root=project_root,
        list_strategies=list_strategies_async,
        run_backtest=run_backtest_async,
        require_backtest_trades=bool(runtime_flags.backtest_require_trades),
        freqtrade_mock_enabled=bool(runtime_flags.freqtrade_mock_enabled),
    )
