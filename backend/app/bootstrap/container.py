from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..lifecycle.service import AppLifecycleService
from ..runtime.blocking import configure_blocking_executor
from ..core.config import Settings
from .container_accessors import AppContainerAccessors
from .container_builders import (
    build_backtest_service,
    build_domain_core,
    build_read_core_services,
    build_read_repair_service,
    build_replay_services,
)
from .container_contexts import (
    CoreContainerContext,
    DevContainerContext,
    FactorContainerContext,
    MarketContainerContext,
    ReadContainerContext,
    ReplayContainerContext,
    StoreContainerContext,
)
from ..market.runtime_builder import MarketRuntimeBuildOptions, build_market_runtime
from ..runtime.api_gates import ApiGateConfig
from ..runtime.flags import RuntimeFlags, load_runtime_flags
from ..runtime.metrics import RuntimeMetrics
from ..storage import PostgresPool, PostgresPoolSettings, bootstrap_postgres_schema
from ..worktree.manager import WorktreeManager


@dataclass(frozen=True)
class AppContainer(AppContainerAccessors):
    project_root: Path
    core: CoreContainerContext
    stores: StoreContainerContext
    factor: FactorContainerContext
    read: ReadContainerContext
    replay: ReplayContainerContext
    market: MarketContainerContext
    dev: DevContainerContext


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
        options=MarketRuntimeBuildOptions(
            runtime_flags=runtime_flags,
            feature_orchestrator=core.feature_orchestrator,
        ),
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
    core_ctx = CoreContainerContext(
        settings=settings,
        runtime_flags=runtime_flags,
        api_gates=api_gates,
        debug_hub=core.debug_hub,
        runtime_metrics=runtime_metrics,
        worktree_manager=worktree_manager,
    )
    store_ctx = StoreContainerContext(
        store=core.store,
        factor_store=core.factor_store,
        feature_store=core.feature_store,
        overlay_store=core.overlay_store,
    )
    factor_ctx = FactorContainerContext(
        factor_orchestrator=core.factor_orchestrator,
        factor_slices_service=core.factor_slices_service,
        factor_read_service=read_core_services.factor_read_service,
        feature_orchestrator=core.feature_orchestrator,
        feature_read_service=read_core_services.feature_read_service,
        ledger_sync_service=ledger_sync_service,
        overlay_orchestrator=core.overlay_orchestrator,
    )
    read_ctx = ReadContainerContext(
        draw_read_service=read_core_services.draw_read_service,
        world_read_service=read_core_services.world_read_service,
        read_repair_service=read_repair_service,
    )
    replay_ctx = ReplayContainerContext(
        replay_prepare_service=replay_services.replay_prepare_service,
        replay_service=replay_services.replay_service,
    )
    market_ctx = MarketContainerContext(
        market_runtime=runtime_build.runtime,
        lifecycle=lifecycle,
    )
    dev_ctx = DevContainerContext(backtest_service=backtest_service)
    return AppContainer(
        project_root=project_root,
        core=core_ctx,
        stores=store_ctx,
        factor=factor_ctx,
        read=read_ctx,
        replay=replay_ctx,
        market=market_ctx,
        dev=dev_ctx,
    )
