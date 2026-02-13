from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..debug.hub import DebugHub
from .fingerprint import build_series_fingerprint
from .fingerprint_rebuild import FactorFingerprintRebuildCoordinator
from .graph import FactorGraph, FactorSpec
from .ingest_outputs import build_head_snapshots, persist_ingest_outputs
from .orchestrator_ingest import ingest_closed
from .orchestrator_ops import (
    build_incremental_bootstrap_state,
    collect_rebuild_event_buckets,
    run_tick_steps,
    run_ticks,
)
from .ingest_window import FactorIngestWindowPlanner
from .manifest import build_default_factor_manifest
from .processor_anchor import AnchorProcessor
from .registry import FactorRegistry
from .rebuild_loader import FactorBootstrapState, FactorRebuildStateLoader, RebuildEventBuckets
from .tick_executor import FactorTickExecutionResult, FactorTickExecutor, FactorTickState
from .runtime_contract import FactorRuntimeContext
from .runtime_config import (
    FactorSettings,
)
from .store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint
from ..store import CandleStore


@dataclass(frozen=True)
class FactorIngestResult:
    rebuilt: bool = False
    fingerprint: str | None = None


class FactorOrchestrator:
    """
    v1 factor orchestrator (incremental):
    - Triggered by closed candles only.
    - Persists minimal factor history (append-only):
      - Pivot.major (confirmed, delayed visibility)
      - Pivot.minor (confirmed, delayed visibility; segment-scoped)
      - Pen.confirmed (confirmed pens, delayed by next reverse pivot)
      - Zhongshu.dead (append-only; derived from confirmed pens)
      - Anchor.switch (append-only; strong_pen + zhongshu_entry)
    """

    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        settings: FactorSettings | None = None,
        ingest_enabled: bool = True,
        fingerprint_rebuild_enabled: bool = True,
        factor_rebuild_keep_candles: int = 2000,
        logic_version_override: str = "",
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._settings = settings or FactorSettings()
        self._ingest_enabled = bool(ingest_enabled)
        self._fingerprint_rebuild_enabled_flag = bool(fingerprint_rebuild_enabled)
        self._factor_rebuild_keep_candles = max(100, int(factor_rebuild_keep_candles))
        self._logic_version_override = str(logic_version_override or "")
        self._debug_hub: DebugHub | None = None
        manifest = build_default_factor_manifest()
        self._registry = FactorRegistry(list(manifest.tick_plugins))
        self._anchor_processor = cast(AnchorProcessor, self._registry.require("anchor"))
        self._graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in self._registry.specs()])
        self._tick_runtime = FactorRuntimeContext(anchor_processor=self._anchor_processor)

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

    def _fingerprint_rebuild_enabled(self) -> bool:
        return bool(self._fingerprint_rebuild_enabled_flag)

    def _build_series_fingerprint(self, *, series_id: str, settings: FactorSettings) -> str:
        return build_series_fingerprint(
            series_id=series_id,
            settings=settings,
            graph=self._graph,
            registry=self._registry,
            orchestrator_file=Path(__file__),
            logic_version_override=self._logic_version_override,
        )

    def enabled(self) -> bool:
        return bool(self._ingest_enabled)

    def head_time(self, series_id: str) -> int | None:
        return self._factor_store.head_time(series_id)

    def _load_settings(self) -> FactorSettings:
        return self._settings

    def _tick_executor(self) -> FactorTickExecutor:
        return FactorTickExecutor(
            graph=self._graph,
            registry=self._registry,
            runtime=self._tick_runtime,
        )

    def _run_tick_steps(self, *, series_id: str, state: FactorTickState) -> None:
        run_tick_steps(tick_executor=self._tick_executor(), series_id=series_id, state=state)

    def _run_ticks(
        self,
        *,
        series_id: str,
        process_times: list[int],
        tf_s: int,
        settings: FactorSettings,
        candles: list[Any],
        time_to_idx: dict[int, int],
        effective_pivots: list[PivotMajorPoint],
        confirmed_pens: list[dict[str, Any]],
        zhongshu_state: dict[str, Any],
        anchor_current_ref: dict[str, Any] | None,
        anchor_strength: float | None,
        last_major_idx: int | None,
        events: list[FactorEventWrite],
    ) -> FactorTickExecutionResult:
        return run_ticks(
            tick_executor=self._tick_executor(),
            series_id=series_id,
            process_times=process_times,
            tf_s=tf_s,
            settings=settings,
            candles=candles,
            time_to_idx=time_to_idx,
            effective_pivots=effective_pivots,
            confirmed_pens=confirmed_pens,
            zhongshu_state=zhongshu_state,
            anchor_current_ref=anchor_current_ref,
            anchor_strength=anchor_strength,
            last_major_idx=last_major_idx,
            events=events,
        )

    def _rebuild_loader(self) -> FactorRebuildStateLoader:
        return FactorRebuildStateLoader(
            factor_store=self._factor_store,
            registry=self._registry,
            graph=self._graph,
            runtime=self._tick_runtime,
            debug_hub=self._debug_hub,
        )

    def _fingerprint_rebuild_coordinator(self) -> FactorFingerprintRebuildCoordinator:
        return FactorFingerprintRebuildCoordinator(
            candle_store=self._candle_store,
            factor_store=self._factor_store,
            debug_hub=self._debug_hub,
            keep_candles=self._factor_rebuild_keep_candles,
        )

    def _ingest_window_planner(self) -> FactorIngestWindowPlanner:
        return FactorIngestWindowPlanner(candle_store=self._candle_store)

    def _collect_rebuild_event_buckets(
        self,
        *,
        series_id: str,
        state_start: int,
        head_time: int,
        scan_limit: int,
    ) -> RebuildEventBuckets:
        return collect_rebuild_event_buckets(
            loader=self._rebuild_loader(),
            series_id=series_id,
            state_start=state_start,
            head_time=head_time,
            scan_limit=scan_limit,
        )

    def _build_head_snapshots(
        self,
        *,
        series_id: str,
        confirmed_pens: list[dict[str, Any]],
        effective_pivots: list[PivotMajorPoint],
        zhongshu_state: dict[str, Any],
        anchor_current_ref: dict[str, Any] | None,
        candles: list[Any],
        up_to: int,
    ) -> dict[str, dict[str, Any]]:
        return build_head_snapshots(
            series_id=series_id,
            up_to=int(up_to),
            candles=candles,
            effective_pivots=effective_pivots,
            confirmed_pens=confirmed_pens,
            zhongshu_state=zhongshu_state,
            anchor_current_ref=anchor_current_ref,
            topo_order=[str(name) for name in self._graph.topo_order],
            registry=self._registry,
            runtime=self._tick_runtime,
        )

    def _persist_ingest_outputs(
        self,
        *,
        series_id: str,
        up_to: int,
        events: list[FactorEventWrite],
        head_snapshots: dict[str, dict[str, Any]],
        auto_rebuild: bool,
        fingerprint: str,
    ) -> int:
        return persist_ingest_outputs(
            factor_store=self._factor_store,
            topo_order=[str(name) for name in self._graph.topo_order],
            series_id=series_id,
            up_to=int(up_to),
            events=events,
            head_snapshots=head_snapshots,
            auto_rebuild=bool(auto_rebuild),
            fingerprint=str(fingerprint),
        )

    def _build_incremental_bootstrap_state(
        self,
        *,
        series_id: str,
        head_time: int,
        lookback_candles: int,
        tf_s: int,
        state_rebuild_event_limit: int,
        candles: list[Any],
        time_to_idx: dict[int, int],
    ) -> FactorBootstrapState:
        return build_incremental_bootstrap_state(
            loader=self._rebuild_loader(),
            series_id=series_id,
            head_time=head_time,
            lookback_candles=lookback_candles,
            tf_s=tf_s,
            state_rebuild_event_limit=state_rebuild_event_limit,
            candles=candles,
            time_to_idx=time_to_idx,
        )

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> FactorIngestResult:
        return ingest_closed(
            self,
            result_cls=FactorIngestResult,
            series_id=series_id,
            up_to_candle_time=up_to_candle_time,
        )
