from __future__ import annotations

from typing import Annotated, Awaitable, Callable

from fastapi import Depends

from ..container import AppContainer
from ..ingest.supervisor import IngestSupervisor
from ..market_data import DefaultMarketDataOrchestrator, WsMessageParser, WsSubscriptionCoordinator
from ..market.backfill_tracker import MarketBackfillProgressTracker
from ..market.ingest_service import MarketIngestService
from ..market.ledger_warmup_service import MarketLedgerWarmupService
from ..market.list import BinanceMarketListService, MinIntervalLimiter
from ..market.query_service import MarketQueryService
from ..market.runtime import MarketIngestContext, MarketReadContext, MarketRealtimeContext
from ..whitelist import MarketWhitelist
from .core import get_app_container

MarketDerivedInitialBackfillHandler = Callable[..., Awaitable[None]]


def get_market_read_context(container: AppContainer = Depends(get_app_container)) -> MarketReadContext:
    return container.market_runtime.read_ctx


def get_market_ingest_context(container: AppContainer = Depends(get_app_container)) -> MarketIngestContext:
    return container.market_runtime.ingest_ctx


def get_market_realtime_context(container: AppContainer = Depends(get_app_container)) -> MarketRealtimeContext:
    return container.market_runtime.realtime_ctx


def get_market_ingest_service(ingest_ctx: MarketIngestContext = Depends(get_market_ingest_context)) -> MarketIngestService:
    return ingest_ctx.ingest


def get_market_query_service(read_ctx: MarketReadContext = Depends(get_market_read_context)) -> MarketQueryService:
    return read_ctx.query


def get_market_ledger_warmup_service(
    read_ctx: MarketReadContext = Depends(get_market_read_context),
) -> MarketLedgerWarmupService:
    return read_ctx.ledger_warmup


def get_market_data(read_ctx: MarketReadContext = Depends(get_market_read_context)) -> DefaultMarketDataOrchestrator:
    return read_ctx.market_data


def get_market_backfill_progress(
    read_ctx: MarketReadContext = Depends(get_market_read_context),
) -> MarketBackfillProgressTracker:
    return read_ctx.backfill_progress


def get_market_whitelist(read_ctx: MarketReadContext = Depends(get_market_read_context)) -> MarketWhitelist:
    return read_ctx.whitelist


def get_market_list_service(read_ctx: MarketReadContext = Depends(get_market_read_context)) -> BinanceMarketListService:
    return read_ctx.market_list


def get_market_force_limiter(read_ctx: MarketReadContext = Depends(get_market_read_context)) -> MinIntervalLimiter:
    return read_ctx.force_limiter


def get_market_ws_messages(realtime_ctx: MarketRealtimeContext = Depends(get_market_realtime_context)) -> WsMessageParser:
    return realtime_ctx.ws_messages


def get_market_ws_subscriptions(
    realtime_ctx: MarketRealtimeContext = Depends(get_market_realtime_context),
) -> WsSubscriptionCoordinator:
    return realtime_ctx.ws_subscriptions


def get_market_derived_initial_backfill(
    realtime_ctx: MarketRealtimeContext = Depends(get_market_realtime_context),
) -> MarketDerivedInitialBackfillHandler:
    return realtime_ctx.derived_initial_backfill


def get_market_ws_catchup_limit(realtime_ctx: MarketRealtimeContext = Depends(get_market_realtime_context)) -> int:
    return int(realtime_ctx.ws_catchup_limit)


def get_ingest_supervisor(ingest_ctx: MarketIngestContext = Depends(get_market_ingest_context)) -> IngestSupervisor:
    return ingest_ctx.supervisor


MarketReadContextDep = Annotated[MarketReadContext, Depends(get_market_read_context)]
MarketIngestContextDep = Annotated[MarketIngestContext, Depends(get_market_ingest_context)]
MarketRealtimeContextDep = Annotated[MarketRealtimeContext, Depends(get_market_realtime_context)]
MarketIngestServiceDep = Annotated[MarketIngestService, Depends(get_market_ingest_service)]
MarketQueryServiceDep = Annotated[MarketQueryService, Depends(get_market_query_service)]
MarketLedgerWarmupServiceDep = Annotated[MarketLedgerWarmupService, Depends(get_market_ledger_warmup_service)]
MarketDataDep = Annotated[DefaultMarketDataOrchestrator, Depends(get_market_data)]
MarketBackfillProgressDep = Annotated[MarketBackfillProgressTracker, Depends(get_market_backfill_progress)]
MarketWhitelistDep = Annotated[MarketWhitelist, Depends(get_market_whitelist)]
MarketListServiceDep = Annotated[BinanceMarketListService, Depends(get_market_list_service)]
MarketForceLimiterDep = Annotated[MinIntervalLimiter, Depends(get_market_force_limiter)]
MarketWsMessagesDep = Annotated[WsMessageParser, Depends(get_market_ws_messages)]
MarketWsSubscriptionsDep = Annotated[WsSubscriptionCoordinator, Depends(get_market_ws_subscriptions)]
MarketDerivedInitialBackfillDep = Annotated[
    MarketDerivedInitialBackfillHandler,
    Depends(get_market_derived_initial_backfill),
]
MarketWsCatchupLimitDep = Annotated[int, Depends(get_market_ws_catchup_limit)]
IngestSupervisorDep = Annotated[IngestSupervisor, Depends(get_ingest_supervisor)]
