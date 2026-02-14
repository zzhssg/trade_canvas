from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Settings
from ..debug.hub import DebugHub
from ..factor.orchestrator import FactorOrchestrator
from ..market.history_bootstrapper import backfill_tail_from_freqtrade
from ..ingest.config import (
    IngestDerivedConfig,
    IngestGuardrailConfig,
    IngestRoleConfig,
    IngestRuntimeConfig,
    IngestWsConfig,
)
from ..ingest.supervisor import IngestSupervisor
from ..ledger.sync_service import LedgerSyncService
from ..pipelines import IngestPipeline
from ..runtime.flags import RuntimeFlags
from ..runtime.metrics import RuntimeMetrics
from ..storage.candle_store import CandleStore
from ..market.whitelist import load_market_whitelist
from ..ws.hub import CandleHub
from .backfill import backfill_market_gap_best_effort
from .backfill_tracker import MarketBackfillProgressTracker
from .ingest_service import MarketIngestService
from .ledger_warmup_service import MarketLedgerWarmupService
from .list import BinanceMarketListService, MinIntervalLimiter
from .query_service import MarketQueryService
from .runtime import MarketIngestContext, MarketReadContext
from ..market_data import (
    DefaultMarketDataOrchestrator,
    HubWsDeliveryService,
    StoreBackfillService,
    StoreCandleReadService,
    StoreFreshnessService,
    build_gap_backfill_handler,
)
from ..overlay.orchestrator import OverlayOrchestrator


@dataclass(frozen=True)
class ReadBuildResult:
    context: MarketReadContext
    whitelist_ingest_on: bool


@dataclass(frozen=True)
class ReadContextBuildRequest:
    settings: Settings
    store: CandleStore
    hub: CandleHub
    debug_hub: DebugHub
    ledger_sync_service: LedgerSyncService
    runtime_flags: RuntimeFlags
    runtime_metrics: RuntimeMetrics


def build_read_context(request: ReadContextBuildRequest) -> ReadBuildResult:
    backfill_state_path = None
    if bool(request.runtime_flags.enable_market_backfill_progress_persistence):
        backfill_state_path = request.settings.db_path.parent / "runtime_state" / "market_backfill_progress.json"
    backfill_progress = MarketBackfillProgressTracker(state_path=backfill_state_path)
    reader_service = StoreCandleReadService(store=request.store)
    backfill_service = StoreBackfillService(
        store=request.store,
        gap_backfill_fn=lambda **kwargs: backfill_market_gap_best_effort(
            enable_ccxt_backfill=bool(request.runtime_flags.enable_ccxt_backfill),
            freqtrade_limit=int(request.runtime_flags.market_gap_backfill_freqtrade_limit),
            market_history_source=str(request.runtime_flags.market_history_source),
            ccxt_timeout_ms=int(request.runtime_flags.ccxt_timeout_ms),
            **kwargs,
        ),
        tail_backfill_fn=lambda s, *, series_id, limit: backfill_tail_from_freqtrade(
            s,
            series_id=series_id,
            limit=limit,
            market_history_source=str(request.runtime_flags.market_history_source),
        ),
        progress_tracker=backfill_progress,
        enable_ccxt_backfill=bool(request.runtime_flags.enable_ccxt_backfill),
        enable_ccxt_backfill_on_read=bool(request.runtime_flags.enable_ccxt_backfill_on_read),
        enable_strict_closed_only=bool(request.runtime_flags.enable_strict_closed_only),
        ccxt_timeout_ms=int(request.runtime_flags.ccxt_timeout_ms),
    )
    request.hub.set_gap_backfill_handler(
        build_gap_backfill_handler(
            reader=reader_service,
            backfill=backfill_service,
            read_limit=request.settings.market_gap_backfill_read_limit,
            enabled=bool(request.runtime_flags.enable_market_gap_backfill),
        )
    )
    market_data = DefaultMarketDataOrchestrator(
        reader=reader_service,
        freshness=StoreFreshnessService(
            store=request.store,
            fresh_window_candles=request.settings.market_fresh_window_candles,
            stale_window_candles=request.settings.market_stale_window_candles,
        ),
        ws_delivery=HubWsDeliveryService(hub=request.hub),
    )
    ledger_warmup_service = MarketLedgerWarmupService(
        runtime_flags=request.runtime_flags,
        debug_hub=request.debug_hub,
        ledger_sync_service=request.ledger_sync_service,
    )
    query_service = MarketQueryService(
        market_data=market_data,
        backfill=backfill_service,
        runtime_flags=request.runtime_flags,
        debug_hub=request.debug_hub,
        runtime_metrics=request.runtime_metrics,
    )
    whitelist = load_market_whitelist(request.settings.whitelist_path)
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
    return ReadBuildResult(
        context=read_context,
        whitelist_ingest_on=bool(request.runtime_flags.enable_whitelist_ingest),
    )


@dataclass(frozen=True)
class IngestContextBuildRequest:
    store: CandleStore
    hub: CandleHub
    factor_orchestrator: FactorOrchestrator
    overlay_orchestrator: OverlayOrchestrator
    debug_hub: DebugHub
    runtime_flags: RuntimeFlags
    runtime_metrics: RuntimeMetrics
    whitelist_series_ids: tuple[str, ...]
    whitelist_ingest_on: bool
    ingest_pipeline: IngestPipeline | None = None


def build_ingest_context(request: IngestContextBuildRequest) -> MarketIngestContext:
    pipeline = request.ingest_pipeline or IngestPipeline(
        store=request.store,
        factor_orchestrator=request.factor_orchestrator,
        overlay_orchestrator=request.overlay_orchestrator,
        hub=request.hub,
        overlay_compensate_on_error=bool(request.runtime_flags.enable_ingest_compensate_overlay_error),
        candle_compensate_on_error=bool(request.runtime_flags.enable_ingest_compensate_new_candles),
    )
    ingest_config = IngestRuntimeConfig(
        derived=IngestDerivedConfig(
            enabled=bool(request.runtime_flags.enable_derived_timeframes),
            base_timeframe=str(request.runtime_flags.derived_base_timeframe),
            timeframes=tuple(request.runtime_flags.derived_timeframes),
            backfill_base_candles=int(request.runtime_flags.derived_backfill_base_candles),
        ),
        ws=IngestWsConfig(
            batch_max=int(request.runtime_flags.binance_ws_batch_max),
            flush_s=float(request.runtime_flags.binance_ws_flush_s),
            forming_min_interval_ms=int(request.runtime_flags.market_forming_min_interval_ms),
        ),
        guardrail=IngestGuardrailConfig(
            enabled=bool(request.runtime_flags.enable_ingest_loop_guardrail),
        ),
        role=IngestRoleConfig(
            guard_enabled=bool(request.runtime_flags.enable_ingest_role_guard),
            ingest_role=str(request.runtime_flags.ingest_role),
        ),
        ondemand_max_jobs=int(request.runtime_flags.ondemand_max_jobs),
        market_history_source=str(request.runtime_flags.market_history_source),
    )
    supervisor = IngestSupervisor(
        store=request.store,
        hub=request.hub,
        whitelist_series_ids=request.whitelist_series_ids,
        ondemand_idle_ttl_s=int(request.runtime_flags.ondemand_idle_ttl_s),
        whitelist_ingest_enabled=bool(request.whitelist_ingest_on),
        ingest_pipeline=pipeline,
        config=ingest_config,
    )
    ingest_service = MarketIngestService(
        hub=request.hub,
        debug_hub=request.debug_hub,
        ingest_pipeline=pipeline,
        debug_api_enabled=bool(request.runtime_flags.enable_debug_api),
        runtime_metrics=request.runtime_metrics,
    )
    return MarketIngestContext(
        supervisor=supervisor,
        ingest=ingest_service,
        ingest_pipeline=pipeline,
    )
