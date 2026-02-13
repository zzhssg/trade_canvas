from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..lifecycle.service import AppLifecycleService
from ..runtime.blocking import configure_blocking_executor
from ..core.config import Settings
from .container_builders import (
    build_backtest_service,
    build_domain_core,
    build_read_core_services,
    build_read_repair_service,
    build_replay_services,
)
from ..backtest.service import BacktestService
from ..debug.hub import DebugHub
from ..factor.orchestrator import FactorOrchestrator
from ..factor.slices_service import FactorSlicesService
from ..factor.store import FactorStore
from ..runtime.flags import RuntimeFlags, load_runtime_flags
from ..ledger.sync_service import LedgerSyncService
from ..market.runtime import MarketRuntime
from ..market.runtime_builder import build_market_runtime
from ..overlay.orchestrator import OverlayOrchestrator
from ..overlay.package_service_v1 import OverlayReplayPackageServiceV1
from ..overlay.store import OverlayStore
from ..read_models import DrawReadService, FactorReadService, ReadRepairService, WorldReadService
from ..replay.prepare_service import ReplayPrepareService
from ..replay.package_service_v1 import ReplayPackageServiceV1
from ..runtime.api_gates import ApiGateConfig
from ..runtime.flags import RuntimeFlags, load_runtime_flags
from ..runtime.metrics import RuntimeMetrics
from ..storage.candle_store import CandleStore
from ..storage import PostgresPool, PostgresPoolSettings, bootstrap_postgres_schema
from ..worktree.manager import WorktreeManager


@dataclass(frozen=True)
class AppContainer:
    project_root: Path
    settings: Settings
    runtime_flags: RuntimeFlags
    api_gates: ApiGateConfig
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


def _maybe_bootstrap_postgres(*, settings: Settings, runtime_flags: RuntimeFlags) -> PostgresPool | None:
    pg_required = bool(runtime_flags.enable_pg_store or runtime_flags.enable_pg_only)
    if not pg_required:
        return None
    if bool(runtime_flags.enable_pg_only) and not bool(runtime_flags.enable_pg_store):
        raise ValueError("pg_store_required_when_pg_only_enabled")
    dsn = str(settings.postgres_dsn or "").strip()
    if not dsn:
        raise ValueError("postgres_dsn_required_when_pg_store_enabled")

    pool = PostgresPool(
        PostgresPoolSettings(
            dsn=dsn,
            connect_timeout_s=float(settings.postgres_connect_timeout_s),
            min_size=int(settings.postgres_pool_min_size),
            max_size=int(settings.postgres_pool_max_size),
        )
    )
    bootstrap_postgres_schema(
        pool=pool,
        schema=settings.postgres_schema,
        enable_timescale=True,
    )
    return pool


def build_app_container(*, settings: Settings, project_root: Path) -> AppContainer:
    runtime_flags = load_runtime_flags()
    api_gates = ApiGateConfig(
        debug_api=bool(runtime_flags.enable_debug_api),
        dev_api=bool(runtime_flags.enable_dev_api),
        read_repair_api=bool(runtime_flags.enable_read_repair_api),
        kline_health_v2=bool(runtime_flags.enable_kline_health_v2),
        kline_health_backfill_recent_seconds=int(runtime_flags.kline_health_backfill_recent_seconds),
        runtime_metrics=bool(runtime_flags.enable_runtime_metrics),
        capacity_metrics=bool(runtime_flags.enable_capacity_metrics),
    )
    postgres_pool = _maybe_bootstrap_postgres(settings=settings, runtime_flags=runtime_flags)
    configure_blocking_executor(workers=int(runtime_flags.blocking_workers))
    runtime_metrics = RuntimeMetrics(enabled=bool(runtime_flags.enable_runtime_metrics))
    core = build_domain_core(
        settings=settings,
        runtime_flags=runtime_flags,
        postgres_pool=postgres_pool,
    )
    read_core_services = build_read_core_services(core=core, runtime_flags=runtime_flags)

    runtime_build = build_market_runtime(
        settings=settings,
        store=core.store,
        factor_orchestrator=core.factor_orchestrator,
        overlay_orchestrator=core.overlay_orchestrator,
        debug_hub=core.debug_hub,
        runtime_metrics=runtime_metrics,
        runtime_flags=runtime_flags,
    )
    lifecycle = AppLifecycleService(market_runtime=runtime_build.runtime)
    ingest_pipeline = runtime_build.runtime.ingest_ctx.ingest_pipeline
    ledger_sync_service = runtime_build.ledger_sync_service
    read_repair_service = build_read_repair_service(
        core=core,
        runtime_flags=runtime_flags,
        ledger_sync_service=ledger_sync_service,
    )
    replay_services = build_replay_services(
        core=core,
        runtime_flags=runtime_flags,
        ingest_pipeline=ingest_pipeline,
        ledger_sync_service=ledger_sync_service,
    )
    backtest_service = build_backtest_service(
        settings=settings,
        project_root=project_root,
        runtime_flags=runtime_flags,
    )
    worktree_manager = WorktreeManager(repo_root=project_root)
    return AppContainer(
        project_root=project_root,
        settings=settings,
        runtime_flags=runtime_flags,
        api_gates=api_gates,
        store=core.store,
        factor_store=core.factor_store,
        factor_orchestrator=core.factor_orchestrator,
        factor_slices_service=core.factor_slices_service,
        factor_read_service=read_core_services.factor_read_service,
        draw_read_service=read_core_services.draw_read_service,
        world_read_service=read_core_services.world_read_service,
        read_repair_service=read_repair_service,
        ledger_sync_service=ledger_sync_service,
        overlay_store=core.overlay_store,
        overlay_orchestrator=core.overlay_orchestrator,
        replay_prepare_service=replay_services.replay_prepare_service,
        replay_service=replay_services.replay_service,
        overlay_pkg_service=replay_services.overlay_pkg_service,
        backtest_service=backtest_service,
        debug_hub=core.debug_hub,
        runtime_metrics=runtime_metrics,
        market_runtime=runtime_build.runtime,
        lifecycle=lifecycle,
        worktree_manager=worktree_manager,
    )
