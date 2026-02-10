from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .debug_hub import DebugHub
from .factor_orchestrator import FactorOrchestrator
from .flags import FeatureFlags
from .ingest_supervisor import IngestSupervisor
from .market_data import (
    DefaultMarketDataOrchestrator,
    StoreBackfillService,
    StoreCandleReadService,
    WsMessageParser,
    WsSubscriptionCoordinator,
)
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .overlay_orchestrator import OverlayOrchestrator
from .pipelines import IngestPipeline
from .store import CandleStore
from .whitelist import MarketWhitelist
from .ws_hub import CandleHub


@dataclass(frozen=True)
class MarketRuntime:
    store: CandleStore
    factor_orchestrator: FactorOrchestrator
    overlay_orchestrator: OverlayOrchestrator
    debug_hub: DebugHub
    hub: CandleHub
    reader: StoreCandleReadService
    backfill: StoreBackfillService
    market_data: DefaultMarketDataOrchestrator
    whitelist: MarketWhitelist
    market_list: BinanceMarketListService
    force_limiter: MinIntervalLimiter
    supervisor: IngestSupervisor
    ws_subscriptions: WsSubscriptionCoordinator
    ws_messages: WsMessageParser
    derived_initial_backfill: Callable[..., Awaitable[None]]
    ws_catchup_limit: int
    ingest_pipeline: IngestPipeline
    flags: FeatureFlags
