from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from ..debug.hub import DebugHub
from ..factor.orchestrator import FactorOrchestrator
from ..ingest.supervisor import IngestSupervisor
from ..market_data import (
    DefaultMarketDataOrchestrator,
    StoreBackfillService,
    StoreCandleReadService,
    WsMessageParser,
    WsSubscriptionCoordinator,
)
from .ledger_warmup_service import MarketLedgerWarmupService
from .list import BinanceMarketListService, MinIntervalLimiter
from .ingest_service import MarketIngestService
from .query_service import MarketQueryService
from ..overlay.orchestrator import OverlayOrchestrator
from ..store import CandleStore
from ..whitelist import MarketWhitelist
from ..ws.hub import CandleHub
from .backfill_tracker import MarketBackfillProgressTracker

if TYPE_CHECKING:
    from ..flags import FeatureFlags
    from ..ledger.sync_service import LedgerSyncService
    from ..pipelines import IngestPipeline
    from ..runtime.flags import RuntimeFlags
    from ..runtime.metrics import RuntimeMetrics


@dataclass(frozen=True)
class MarketReadContext:
    reader: StoreCandleReadService
    backfill: StoreBackfillService
    market_data: DefaultMarketDataOrchestrator
    ledger_warmup: MarketLedgerWarmupService
    backfill_progress: MarketBackfillProgressTracker
    whitelist: MarketWhitelist
    market_list: BinanceMarketListService
    force_limiter: MinIntervalLimiter
    query: MarketQueryService


@dataclass(frozen=True)
class MarketIngestContext:
    supervisor: IngestSupervisor
    ingest: MarketIngestService
    ingest_pipeline: IngestPipeline


@dataclass(frozen=True)
class MarketRealtimeContext:
    ws_subscriptions: WsSubscriptionCoordinator
    ws_messages: WsMessageParser
    derived_initial_backfill: Callable[..., Awaitable[None]]
    ws_catchup_limit: int = 5000


@dataclass(frozen=True)
class MarketRuntime:
    store: CandleStore
    factor_orchestrator: FactorOrchestrator
    overlay_orchestrator: OverlayOrchestrator
    debug_hub: DebugHub
    hub: CandleHub
    flags: FeatureFlags
    runtime_flags: RuntimeFlags
    runtime_metrics: RuntimeMetrics
    ledger_sync_service: LedgerSyncService
    read_ctx: MarketReadContext
    ingest_ctx: MarketIngestContext
    realtime_ctx: MarketRealtimeContext
