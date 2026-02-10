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
from .market_runtime import MarketRuntime
from .market_runtime_builder import build_market_runtime
from .overlay_orchestrator import OverlayOrchestrator
from .overlay_package_service_v1 import OverlayReplayPackageServiceV1
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .read_models import DrawReadService, FactorReadService
from .replay_package_service_v1 import ReplayPackageServiceV1
from .schemas import GetFactorSlicesResponseV1
from .store import CandleStore
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
    factor_read_service: FactorReadService
    draw_read_service: DrawReadService
    overlay_store: OverlayStore
    overlay_orchestrator: OverlayOrchestrator
    replay_service: ReplayPackageServiceV1
    overlay_pkg_service: OverlayReplayPackageServiceV1
    debug_hub: DebugHub
    hub: CandleHub
    ingest_pipeline: IngestPipeline
    market_runtime: MarketRuntime
    supervisor: IngestSupervisor
    whitelist_ingest_enabled: bool
    read_factor_slices: Callable[..., GetFactorSlicesResponseV1]


def build_app_container(*, settings: Settings, project_root: Path) -> AppContainer:
    flags = load_feature_flags()

    store = CandleStore(db_path=settings.db_path)
    factor_store = FactorStore(db_path=settings.db_path)
    factor_orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)
    factor_slices_service = FactorSlicesService(candle_store=store, factor_store=factor_store)

    overlay_store = OverlayStore(db_path=settings.db_path)
    overlay_orchestrator = OverlayOrchestrator(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
    )

    debug_hub = DebugHub()
    factor_orchestrator.set_debug_hub(debug_hub)
    overlay_orchestrator.set_debug_hub(debug_hub)

    factor_read_service = FactorReadService(
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        strict_mode=bool(flags.enable_read_strict_mode),
    )
    draw_read_service = DrawReadService(
        store=store,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        factor_read_service=factor_read_service,
        debug_hub=debug_hub,
        debug_api_fallback=bool(flags.enable_debug_api),
    )

    runtime_build = build_market_runtime(
        settings=settings,
        store=store,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        debug_hub=debug_hub,
        flags=flags,
    )

    ingest_pipeline = runtime_build.runtime.ingest_pipeline
    if ingest_pipeline is None:
        raise RuntimeError("market runtime missing ingest pipeline")

    replay_service = ReplayPackageServiceV1(
        candle_store=store,
        factor_store=factor_store,
        overlay_store=overlay_store,
        factor_slices_service=factor_slices_service,
        ingest_pipeline=ingest_pipeline,
        enable_ingest_pipeline_v2=bool(flags.enable_ingest_pipeline_v2),
    )
    overlay_pkg_service = OverlayReplayPackageServiceV1(candle_store=store, overlay_store=overlay_store)

    def read_factor_slices(*, series_id: str, at_time: int, window_candles: int) -> GetFactorSlicesResponseV1:
        return factor_read_service.read_slices(
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    return AppContainer(
        project_root=project_root,
        settings=settings,
        flags=flags,
        store=store,
        factor_store=factor_store,
        factor_orchestrator=factor_orchestrator,
        factor_slices_service=factor_slices_service,
        factor_read_service=factor_read_service,
        draw_read_service=draw_read_service,
        overlay_store=overlay_store,
        overlay_orchestrator=overlay_orchestrator,
        replay_service=replay_service,
        overlay_pkg_service=overlay_pkg_service,
        debug_hub=debug_hub,
        hub=runtime_build.hub,
        ingest_pipeline=ingest_pipeline,
        market_runtime=runtime_build.runtime,
        supervisor=runtime_build.supervisor,
        whitelist_ingest_enabled=runtime_build.whitelist_ingest_on,
        read_factor_slices=read_factor_slices,
    )
