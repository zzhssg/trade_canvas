from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from ..core.config import Settings
from ..debug.hub import DebugHub
from ..factor.orchestrator import FactorOrchestrator
from ..feature.orchestrator import FeatureOrchestrator
from ..ingest.supervisor import IngestSupervisor
from ..ledger.sync_service import LedgerSyncService
from .runtime_components import (
    IngestContextBuildRequest,
    ReadContextBuildRequest,
    build_ingest_context,
    build_read_context,
)
from ..market_data import (
    WsMessageParser,
    WsSubscriptionCoordinator,
    build_derived_initial_backfill_handler,
)
from .runtime import (
    MarketRealtimeContext,
    MarketRuntime,
)
from ..pipelines import IngestPipeline
from ..overlay.orchestrator import OverlayOrchestrator
from ..runtime.flags import RuntimeFlags, load_runtime_flags
from ..runtime.metrics import RuntimeMetrics
from ..storage.candle_store import CandleStore
from ..ws.hub import CandleHub
from ..ws_publishers import RedisWsPublisher, WsPublisher


@dataclass(frozen=True)
class MarketRuntimeBuildResult:
    runtime: MarketRuntime
    ledger_sync_service: LedgerSyncService


@dataclass(frozen=True)
class MarketRuntimeBuildOptions:
    runtime_flags: RuntimeFlags | None = None
    ingest_pipeline: IngestPipeline | None = None
    feature_orchestrator: FeatureOrchestrator | None = None


@dataclass(frozen=True)
class _RuntimeBootstrap:
    runtime_flags: RuntimeFlags
    hub: CandleHub
    ingest_pipeline: IngestPipeline
    ledger_sync_service: LedgerSyncService


def _build_ws_publisher(*, settings: Settings, runtime_flags: RuntimeFlags) -> WsPublisher | None:
    if not bool(runtime_flags.enable_ws_pubsub):
        return None
    redis_url = str(settings.redis_url or "").strip()
    if not redis_url:
        raise ValueError("redis_url_required_when_ws_pubsub_enabled")
    return RedisWsPublisher(redis_url=redis_url)


def _build_runtime_bootstrap(
    *,
    settings: Settings,
    store: CandleStore,
    factor_orchestrator: FactorOrchestrator,
    feature_orchestrator: FeatureOrchestrator | None,
    overlay_orchestrator: OverlayOrchestrator,
    runtime_flags: RuntimeFlags | None,
    ingest_pipeline: IngestPipeline | None,
) -> _RuntimeBootstrap:
    effective_runtime_flags = runtime_flags or load_runtime_flags()
    hub = CandleHub(
        publisher=_build_ws_publisher(
            settings=settings,
            runtime_flags=effective_runtime_flags,
        )
    )
    if ingest_pipeline is None:
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor_orchestrator,
            feature_orchestrator=feature_orchestrator,
            overlay_orchestrator=overlay_orchestrator,
            hub=hub,
            overlay_compensate_on_error=bool(effective_runtime_flags.enable_ingest_compensate_overlay_error),
            candle_compensate_on_error=bool(effective_runtime_flags.enable_ingest_compensate_new_candles),
        )
    else:
        pipeline = ingest_pipeline
    ledger_sync_service = LedgerSyncService(
        store=store,
        factor_store=factor_orchestrator,
        overlay_store=overlay_orchestrator,
        ingest_pipeline=pipeline,
    )
    return _RuntimeBootstrap(
        runtime_flags=effective_runtime_flags,
        hub=hub,
        ingest_pipeline=pipeline,
        ledger_sync_service=ledger_sync_service,
    )


def _build_derived_initial_backfill(
    *,
    store: CandleStore,
    factor_orchestrator: FactorOrchestrator,
    overlay_orchestrator: OverlayOrchestrator,
    runtime_flags: RuntimeFlags,
) -> Callable[..., Awaitable[None]]:
    return build_derived_initial_backfill_handler(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        derived_enabled=bool(runtime_flags.enable_derived_timeframes),
        derived_base_timeframe=str(runtime_flags.derived_base_timeframe),
        derived_timeframes=tuple(runtime_flags.derived_timeframes),
        derived_backfill_base_candles=int(runtime_flags.derived_backfill_base_candles),
    )


def _build_realtime_context(
    *,
    hub: CandleHub,
    settings: Settings,
    supervisor: IngestSupervisor,
    derived_initial_backfill: Callable[..., Awaitable[None]],
    runtime_metrics: RuntimeMetrics,
) -> MarketRealtimeContext:
    return MarketRealtimeContext(
        ws_subscriptions=WsSubscriptionCoordinator(
            hub=hub,
            ondemand_subscribe=supervisor.subscribe,
            ondemand_unsubscribe=supervisor.unsubscribe,
            runtime_metrics=runtime_metrics,
        ),
        ws_messages=WsMessageParser(),
        derived_initial_backfill=derived_initial_backfill,
        ws_catchup_limit=int(settings.market_ws_catchup_limit),
    )


def build_market_runtime(
    *,
    settings: Settings,
    store: CandleStore,
    factor_orchestrator: FactorOrchestrator,
    overlay_orchestrator: OverlayOrchestrator,
    debug_hub: DebugHub,
    runtime_metrics: RuntimeMetrics,
    options: MarketRuntimeBuildOptions | None = None,
) -> MarketRuntimeBuildResult:
    build_options = options or MarketRuntimeBuildOptions()
    bootstrap = _build_runtime_bootstrap(
        settings=settings,
        store=store,
        factor_orchestrator=factor_orchestrator,
        feature_orchestrator=build_options.feature_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        runtime_flags=build_options.runtime_flags,
        ingest_pipeline=build_options.ingest_pipeline,
    )
    read_build = build_read_context(
        ReadContextBuildRequest(
            settings=settings,
            store=store,
            hub=bootstrap.hub,
            debug_hub=debug_hub,
            ledger_sync_service=bootstrap.ledger_sync_service,
            runtime_flags=bootstrap.runtime_flags,
            runtime_metrics=runtime_metrics,
        )
    )
    derived_initial_backfill = _build_derived_initial_backfill(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        runtime_flags=bootstrap.runtime_flags,
    )
    ingest_context = build_ingest_context(
        IngestContextBuildRequest(
            store=store,
            hub=bootstrap.hub,
            factor_orchestrator=factor_orchestrator,
            overlay_orchestrator=overlay_orchestrator,
            debug_hub=debug_hub,
            runtime_flags=bootstrap.runtime_flags,
            runtime_metrics=runtime_metrics,
            whitelist_series_ids=read_build.context.whitelist.series_ids,
            whitelist_ingest_on=read_build.whitelist_ingest_on,
            feature_orchestrator=build_options.feature_orchestrator,
            ingest_pipeline=bootstrap.ingest_pipeline,
        )
    )
    realtime_context = _build_realtime_context(
        hub=bootstrap.hub,
        settings=settings,
        supervisor=ingest_context.supervisor,
        derived_initial_backfill=derived_initial_backfill,
        runtime_metrics=runtime_metrics,
    )
    market_runtime = MarketRuntime(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        hub=bootstrap.hub,
        runtime_flags=bootstrap.runtime_flags,
        runtime_metrics=runtime_metrics,
        ledger_sync_service=bootstrap.ledger_sync_service,
        read_ctx=read_build.context,
        ingest_ctx=ingest_context,
        realtime_ctx=realtime_context,
    )

    return MarketRuntimeBuildResult(runtime=market_runtime, ledger_sync_service=bootstrap.ledger_sync_service)
