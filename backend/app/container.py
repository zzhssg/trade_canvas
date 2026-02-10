from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .flags import FeatureFlags, load_feature_flags
from .ingest_supervisor import IngestSupervisor
from .market_backfill import backfill_market_gap_best_effort
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
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .market_runtime import MarketRuntime
from .overlay_orchestrator import OverlayOrchestrator
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .read_models import DrawReadService, FactorReadService
from .replay_package_service_v1 import ReplayPackageServiceV1
from .store import CandleStore
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub


@dataclass(frozen=True)
class AppContainer:
    project_root: Path
    settings: Settings
    flags: FeatureFlags
    store: CandleStore
    factor_store: FactorStore
    factor_orchestrator: FactorOrchestrator
    factor_slices_service: FactorSlicesService
    overlay_store: OverlayStore
    overlay_orchestrator: OverlayOrchestrator
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1
    debug_hub: DebugHub
    hub: CandleHub
    ingest_pipeline: IngestPipeline
    factor_read_service: FactorReadService
    draw_read_service: DrawReadService
    market_runtime: MarketRuntime
    supervisor: IngestSupervisor
    whitelist_ingest_enabled: bool


def build_app_container(
    *,
    settings: Settings,
    project_root: Path,
    gap_backfill_fn: Callable[..., int] = backfill_market_gap_best_effort,
) -> AppContainer:
    flags = load_feature_flags()
    store = CandleStore(db_path=settings.db_path)
    factor_store = FactorStore(db_path=settings.db_path)
    factor_orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)
    factor_slices_service = FactorSlicesService(candle_store=store, factor_store=factor_store)
    overlay_store = OverlayStore(db_path=settings.db_path)
    overlay_orchestrator = OverlayOrchestrator(candle_store=store, factor_store=factor_store, overlay_store=overlay_store)
    debug_hub = DebugHub()
    factor_orchestrator.set_debug_hub(debug_hub)
    overlay_orchestrator.set_debug_hub(debug_hub)
    hub = CandleHub()
    ingest_pipeline = IngestPipeline(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        hub=hub,
    )
    factor_read_service = FactorReadService(
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        strict_mode=flags.enable_read_strict_mode,
    )
    draw_read_service = DrawReadService(
        store=store,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        factor_read_service=factor_read_service,
        debug_hub=debug_hub,
        debug_api_fallback=bool(flags.enable_debug_api),
    )

    replay_service = ReplayPackageServiceV1(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        factor_slices_service=factor_slices_service,
        ingest_pipeline=ingest_pipeline,
        enable_ingest_pipeline_v2=flags.enable_ingest_pipeline_v2,
    )
    overlay_pkg_service = OverlayReplayPackageServiceV1(candle_store=store, overlay_store=overlay_store)

    reader_service = StoreCandleReadService(store=store)
    backfill_service = StoreBackfillService(
        store=store,
        gap_backfill_fn=gap_backfill_fn,
    )
    hub.set_gap_backfill_handler(
        build_gap_backfill_handler(
            reader=reader_service,
            backfill=backfill_service,
            read_limit=settings.market_gap_backfill_read_limit,
        )
    )
    derived_initial_backfill = build_derived_initial_backfill_handler(
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        ingest_pipeline=ingest_pipeline,
        enable_ingest_pipeline_v2=flags.enable_ingest_pipeline_v2,
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
    whitelist_ingest_enabled = bool(flags.enable_whitelist_ingest)

    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        whitelist_series_ids=whitelist.series_ids,
        ondemand_idle_ttl_s=int(flags.ondemand_idle_ttl_s),
        whitelist_ingest_enabled=whitelist_ingest_enabled,
        ingest_pipeline=ingest_pipeline,
        enable_ingest_pipeline_v2=flags.enable_ingest_pipeline_v2,
    )
    ws_subscriptions = WsSubscriptionCoordinator(
        hub=hub,
        ondemand_subscribe=supervisor.subscribe,
        ondemand_unsubscribe=supervisor.unsubscribe,
    )
    ws_messages = WsMessageParser()
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
        ws_catchup_limit=int(settings.market_ws_catchup_limit),
        ingest_pipeline=ingest_pipeline,
        flags=flags,
    )

    return AppContainer(
        project_root=project_root,
        settings=settings,
        flags=flags,
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        replay_service=replay_service,
        overlay_pkg_service=overlay_pkg_service,
        debug_hub=debug_hub,
        hub=hub,
        ingest_pipeline=ingest_pipeline,
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        market_runtime=market_runtime,
        supervisor=supervisor,
        whitelist_ingest_enabled=whitelist_ingest_enabled,
    )
