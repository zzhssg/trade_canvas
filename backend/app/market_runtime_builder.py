from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .config import Settings
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .flags import FeatureFlags, load_feature_flags
from .history_bootstrapper import backfill_tail_from_freqtrade
from .ingest_supervisor import IngestSupervisor
from .ledger_sync_service import LedgerSyncService
from .market_backfill import backfill_market_gap_best_effort
from .market_backfill_tracker import MarketBackfillProgressTracker
from .market_data import (
    DefaultMarketDataOrchestrator,
    HubWsDeliveryService,
    StoreBackfillService,
    StoreCandleReadService,
    StoreFreshnessService,
    WsMessageParser,
    WsSubscriptionCoordinator,
    build_derived_initial_backfill_handler,
    build_gap_backfill_handler,
)
from .market_ingest_service import MarketIngestService
from .market_ledger_warmup_service import MarketLedgerWarmupService
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .market_query_service import MarketQueryService
from .market_runtime import (
    MarketIngestContext,
    MarketReadContext,
    MarketRealtimeContext,
    MarketRuntime,
)
from .pipelines import IngestPipeline
from .overlay_orchestrator import OverlayOrchestrator
from .runtime_flags import RuntimeFlags, load_runtime_flags
from .runtime_metrics import RuntimeMetrics
from .store import CandleStore
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub
from .ws_publishers import RedisWsPublisher, WsPublisher


@dataclass(frozen=True)
class MarketRuntimeBuildResult:
    runtime: MarketRuntime
    ledger_sync_service: LedgerSyncService


@dataclass(frozen=True)
class _ReadBuildResult:
    context: MarketReadContext
    whitelist_ingest_on: bool


@dataclass(frozen=True)
class _RuntimeBootstrap:
    flags: FeatureFlags
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
    overlay_orchestrator: OverlayOrchestrator,
    flags: FeatureFlags | None,
    runtime_flags: RuntimeFlags | None,
    ingest_pipeline: IngestPipeline | None,
) -> _RuntimeBootstrap:
    effective_flags = flags or load_feature_flags()
    effective_runtime_flags = runtime_flags or load_runtime_flags(base_flags=effective_flags)
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
        flags=effective_flags,
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


def _build_read_context(
    *,
    settings: Settings,
    store: CandleStore,
    hub: CandleHub,
    debug_hub: DebugHub,
    factor_orchestrator: FactorOrchestrator,
    overlay_orchestrator: OverlayOrchestrator,
    ingest_pipeline: IngestPipeline,
    ledger_sync_service: LedgerSyncService,
    runtime_flags: RuntimeFlags,
    runtime_metrics: RuntimeMetrics,
    flags: FeatureFlags,
) -> _ReadBuildResult:
    backfill_state_path = None
    if bool(runtime_flags.enable_market_backfill_progress_persistence):
        backfill_state_path = settings.db_path.parent / "runtime_state" / "market_backfill_progress.json"
    backfill_progress = MarketBackfillProgressTracker(state_path=backfill_state_path)
    reader_service = StoreCandleReadService(store=store)
    backfill_service = StoreBackfillService(
        store=store,
        gap_backfill_fn=lambda **kwargs: backfill_market_gap_best_effort(
            enable_ccxt_backfill=bool(runtime_flags.enable_ccxt_backfill),
            freqtrade_limit=int(runtime_flags.market_gap_backfill_freqtrade_limit),
            market_history_source=str(runtime_flags.market_history_source),
            ccxt_timeout_ms=int(runtime_flags.ccxt_timeout_ms),
            **kwargs,
        ),
        tail_backfill_fn=lambda s, *, series_id, limit: backfill_tail_from_freqtrade(
            s,
            series_id=series_id,
            limit=limit,
            market_history_source=str(runtime_flags.market_history_source),
        ),
        progress_tracker=backfill_progress,
        enable_ccxt_backfill=bool(runtime_flags.enable_ccxt_backfill),
        enable_ccxt_backfill_on_read=bool(runtime_flags.enable_ccxt_backfill_on_read),
        enable_strict_closed_only=bool(runtime_flags.enable_strict_closed_only),
        ccxt_timeout_ms=int(runtime_flags.ccxt_timeout_ms),
    )
    hub.set_gap_backfill_handler(
        build_gap_backfill_handler(
            reader=reader_service,
            backfill=backfill_service,
            read_limit=settings.market_gap_backfill_read_limit,
            enabled=bool(runtime_flags.enable_market_gap_backfill),
        )
    )
    market_data = DefaultMarketDataOrchestrator(
        reader=reader_service,
        freshness=StoreFreshnessService(
            store=store,
            fresh_window_candles=settings.market_fresh_window_candles,
            stale_window_candles=settings.market_stale_window_candles,
        ),
        ws_delivery=HubWsDeliveryService(hub=hub),
    )
    ledger_warmup_service = MarketLedgerWarmupService(
        runtime_flags=runtime_flags,
        debug_hub=debug_hub,
        ledger_sync_service=ledger_sync_service,
    )
    query_service = MarketQueryService(
        market_data=market_data,
        backfill=backfill_service,
        runtime_flags=runtime_flags,
        debug_hub=debug_hub,
        runtime_metrics=runtime_metrics,
    )
    whitelist = load_market_whitelist(settings.whitelist_path)
    read_context = MarketReadContext(
        reader=reader_service,
        backfill=backfill_service,
        market_data=market_data,
        ledger_warmup=ledger_warmup_service,
        backfill_progress=backfill_progress,
        whitelist=whitelist,
        market_list=BinanceMarketListService(),
        force_limiter=MinIntervalLimiter(min_interval_s=2.0),
        query=query_service,
    )
    return _ReadBuildResult(
        context=read_context,
        whitelist_ingest_on=bool(flags.enable_whitelist_ingest),
    )


def _build_ingest_context(
    *,
    store: CandleStore,
    hub: CandleHub,
    factor_orchestrator: FactorOrchestrator,
    overlay_orchestrator: OverlayOrchestrator,
    debug_hub: DebugHub,
    runtime_flags: RuntimeFlags,
    runtime_metrics: RuntimeMetrics,
    flags: FeatureFlags,
    whitelist_series_ids: tuple[str, ...],
    whitelist_ingest_on: bool,
    ingest_pipeline: IngestPipeline | None = None,
) -> MarketIngestContext:
    pipeline = ingest_pipeline or IngestPipeline(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        hub=hub,
        overlay_compensate_on_error=bool(runtime_flags.enable_ingest_compensate_overlay_error),
        candle_compensate_on_error=bool(runtime_flags.enable_ingest_compensate_new_candles),
    )
    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        whitelist_series_ids=whitelist_series_ids,
        ondemand_idle_ttl_s=int(flags.ondemand_idle_ttl_s),
        ondemand_max_jobs=int(runtime_flags.ondemand_max_jobs),
        whitelist_ingest_enabled=bool(whitelist_ingest_on),
        ingest_pipeline=pipeline,
        market_history_source=str(runtime_flags.market_history_source),
        derived_enabled=bool(runtime_flags.enable_derived_timeframes),
        derived_base_timeframe=str(runtime_flags.derived_base_timeframe),
        derived_timeframes=tuple(runtime_flags.derived_timeframes),
        binance_ws_batch_max=int(runtime_flags.binance_ws_batch_max),
        binance_ws_flush_s=float(runtime_flags.binance_ws_flush_s),
        forming_min_interval_ms=int(runtime_flags.market_forming_min_interval_ms),
        enable_loop_guardrail=bool(runtime_flags.enable_ingest_loop_guardrail),
        enable_role_guard=bool(runtime_flags.enable_ingest_role_guard),
        ingest_role=str(runtime_flags.ingest_role),
    )
    ingest_service = MarketIngestService(
        hub=hub,
        debug_hub=debug_hub,
        ingest_pipeline=pipeline,
        debug_api_enabled=bool(runtime_flags.enable_debug_api),
        runtime_metrics=runtime_metrics,
    )
    return MarketIngestContext(
        supervisor=supervisor,
        ingest=ingest_service,
        ingest_pipeline=pipeline,
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
    flags: FeatureFlags | None = None,
    runtime_flags: RuntimeFlags | None = None,
    ingest_pipeline: IngestPipeline | None = None,
) -> MarketRuntimeBuildResult:
    bootstrap = _build_runtime_bootstrap(
        settings=settings,
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        flags=flags,
        runtime_flags=runtime_flags,
        ingest_pipeline=ingest_pipeline,
    )
    read_build = _build_read_context(
        settings=settings,
        store=store,
        hub=bootstrap.hub,
        debug_hub=debug_hub,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        ingest_pipeline=bootstrap.ingest_pipeline,
        ledger_sync_service=bootstrap.ledger_sync_service,
        runtime_flags=bootstrap.runtime_flags,
        runtime_metrics=runtime_metrics,
        flags=bootstrap.flags,
    )
    derived_initial_backfill = _build_derived_initial_backfill(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        runtime_flags=bootstrap.runtime_flags,
    )
    ingest_context = _build_ingest_context(
        store=store,
        hub=bootstrap.hub,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        runtime_flags=bootstrap.runtime_flags,
        runtime_metrics=runtime_metrics,
        flags=bootstrap.flags,
        whitelist_series_ids=read_build.context.whitelist.series_ids,
        whitelist_ingest_on=read_build.whitelist_ingest_on,
        ingest_pipeline=bootstrap.ingest_pipeline,
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
        flags=bootstrap.flags,
        runtime_flags=bootstrap.runtime_flags,
        runtime_metrics=runtime_metrics,
        ledger_sync_service=bootstrap.ledger_sync_service,
        read_ctx=read_build.context,
        ingest_ctx=ingest_context,
        realtime_ctx=realtime_context,
    )

    return MarketRuntimeBuildResult(runtime=market_runtime, ledger_sync_service=bootstrap.ledger_sync_service)
