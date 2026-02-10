from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .flags import FeatureFlags, load_feature_flags
from .ingest_supervisor import IngestSupervisor
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
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .market_runtime import MarketRuntime
from .pipelines import IngestPipeline
from .overlay_orchestrator import OverlayOrchestrator
from .runtime_flags import RuntimeFlags, load_runtime_flags
from .store import CandleStore
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub


@dataclass(frozen=True)
class MarketRuntimeBuildResult:
    runtime: MarketRuntime
    hub: CandleHub
    supervisor: IngestSupervisor
    whitelist_ingest_on: bool


def build_market_runtime(
    *,
    settings: Settings,
    store: CandleStore,
    factor_orchestrator: FactorOrchestrator,
    overlay_orchestrator: OverlayOrchestrator,
    debug_hub: DebugHub,
    flags: FeatureFlags | None = None,
    runtime_flags: RuntimeFlags | None = None,
    ingest_pipeline: IngestPipeline | None = None,
) -> MarketRuntimeBuildResult:
    effective_flags = flags or load_feature_flags()
    effective_runtime_flags = runtime_flags or load_runtime_flags(base_flags=effective_flags)
    hub = CandleHub()
    backfill_progress = MarketBackfillProgressTracker()
    reader_service = StoreCandleReadService(store=store)
    backfill_service = StoreBackfillService(
        store=store,
        gap_backfill_fn=lambda **kwargs: backfill_market_gap_best_effort(
            enable_ccxt_backfill=bool(effective_runtime_flags.enable_ccxt_backfill),
            freqtrade_limit=int(effective_runtime_flags.market_gap_backfill_freqtrade_limit),
            **kwargs,
        ),
        progress_tracker=backfill_progress,
        enable_ccxt_backfill=bool(effective_runtime_flags.enable_ccxt_backfill),
        enable_ccxt_backfill_on_read=bool(effective_runtime_flags.enable_ccxt_backfill_on_read),
    )
    hub.set_gap_backfill_handler(
        build_gap_backfill_handler(
            reader=reader_service,
            backfill=backfill_service,
            read_limit=settings.market_gap_backfill_read_limit,
            enabled=bool(effective_runtime_flags.enable_market_gap_backfill),
        )
    )
    derived_initial_backfill = build_derived_initial_backfill_handler(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
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
    whitelist = load_market_whitelist(settings.whitelist_path)
    market_list = BinanceMarketListService()
    force_limiter = MinIntervalLimiter(min_interval_s=2.0)

    idle_ttl_s = int(effective_flags.ondemand_idle_ttl_s)
    whitelist_ingest_on = bool(effective_flags.enable_whitelist_ingest)
    pipeline = ingest_pipeline or IngestPipeline(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        hub=hub,
    )

    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        whitelist_series_ids=whitelist.series_ids,
        ondemand_idle_ttl_s=idle_ttl_s,
        ondemand_max_jobs=int(effective_runtime_flags.ondemand_max_jobs),
        whitelist_ingest_enabled=whitelist_ingest_on,
        ingest_pipeline=pipeline,
    )
    ws_subscriptions = WsSubscriptionCoordinator(
        hub=hub,
        ondemand_subscribe=supervisor.subscribe,
        ondemand_unsubscribe=supervisor.unsubscribe,
    )
    ws_messages = WsMessageParser()
    ingest_service = MarketIngestService(
        hub=hub,
        debug_hub=debug_hub,
        ingest_pipeline=pipeline,
    )
    market_runtime = MarketRuntime(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        hub=hub,
        reader=reader_service,
        backfill=backfill_service,
        market_data=market_data,
        whitelist=whitelist,
        market_list=market_list,
        force_limiter=force_limiter,
        supervisor=supervisor,
        ws_subscriptions=ws_subscriptions,
        ws_messages=ws_messages,
        derived_initial_backfill=derived_initial_backfill,
        ingest=ingest_service,
        ws_catchup_limit=int(settings.market_ws_catchup_limit),
        ingest_pipeline=pipeline,
        flags=effective_flags,
        runtime_flags=effective_runtime_flags,
        backfill_progress=backfill_progress,
    )

    return MarketRuntimeBuildResult(
        runtime=market_runtime,
        hub=hub,
        supervisor=supervisor,
        whitelist_ingest_on=whitelist_ingest_on,
    )
