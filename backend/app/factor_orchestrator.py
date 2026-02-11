from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .debug_hub import DebugHub
from .factor_fingerprint import build_series_fingerprint
from .factor_fingerprint_rebuild import FactorFingerprintRebuildCoordinator
from .factor_graph import FactorGraph, FactorSpec
from .factor_ingest_window import FactorIngestWindowPlanner
from .factor_manifest import build_default_factor_manifest
from .factor_processor_anchor import AnchorProcessor
from .factor_registry import FactorRegistry
from .factor_rebuild_loader import FactorBootstrapState, FactorRebuildStateLoader, RebuildEventBuckets
from .factor_tick_executor import FactorTickExecutionResult, FactorTickExecutor, FactorTickState
from .factor_runtime_contract import FactorRuntimeContext
from .factor_runtime_config import (
    FactorSettings,
)
from .factor_store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass(frozen=True)
class FactorIngestResult:
    rebuilt: bool = False
    fingerprint: str | None = None


@dataclass
class _HeadBuildState:
    up_to: int
    candles: list[Any]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None


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
        self._tick_executor().run_tick_steps(series_id=series_id, state=state)

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
        return self._tick_executor().run_incremental(
            series_id=series_id,
            process_times=process_times,
            tf_s=int(tf_s),
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
        return self._rebuild_loader().collect_rebuild_event_buckets(
            series_id=series_id,
            state_start=int(state_start),
            head_time=int(head_time),
            scan_limit=int(scan_limit),
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
        state = _HeadBuildState(
            up_to=int(up_to),
            candles=candles,
            effective_pivots=effective_pivots,
            confirmed_pens=confirmed_pens,
            zhongshu_state=zhongshu_state,
            anchor_current_ref=anchor_current_ref,
        )
        out: dict[str, dict[str, Any]] = {}
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            build_head = getattr(plugin, "build_head_snapshot", None)
            if not callable(build_head):
                continue
            head = build_head(
                series_id=series_id,
                state=state,
                runtime=self._tick_runtime,
            )
            if isinstance(head, dict):
                out[str(factor_name)] = head
        return out

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
        with self._factor_store.connect() as conn:
            before_changes = int(conn.total_changes)
            self._factor_store.insert_events_in_conn(conn, events=events)
            for factor_name in self._graph.topo_order:
                head = head_snapshots.get(str(factor_name))
                if not isinstance(head, dict):
                    continue
                self._factor_store.insert_head_snapshot_in_conn(
                    conn,
                    series_id=series_id,
                    factor_name=str(factor_name),
                    candle_time=int(up_to),
                    head=head,
                )
            self._factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(up_to))
            if auto_rebuild:
                self._factor_store.upsert_series_fingerprint_in_conn(
                    conn,
                    series_id=series_id,
                    fingerprint=fingerprint,
                )
            conn.commit()
            return int(conn.total_changes) - before_changes

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
        return self._rebuild_loader().build_incremental_bootstrap_state(
            series_id=series_id,
            head_time=int(head_time),
            lookback_candles=int(lookback_candles),
            tf_s=int(tf_s),
            state_rebuild_event_limit=int(state_rebuild_event_limit),
            candles=candles,
            time_to_idx=time_to_idx,
        )

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> FactorIngestResult:
        t0 = time.perf_counter()
        if not self.enabled():
            return FactorIngestResult()

        up_to = int(up_to_candle_time or 0)
        if up_to <= 0:
            return FactorIngestResult()

        s = self._load_settings()
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        max_window = max(int(s.pivot_window_major), int(s.pivot_window_minor))
        auto_rebuild = self._fingerprint_rebuild_enabled()
        current_fingerprint = self._build_series_fingerprint(series_id=series_id, settings=s)
        rebuild_outcome = self._fingerprint_rebuild_coordinator().ensure_series_ready(
            series_id=series_id,
            auto_rebuild=bool(auto_rebuild),
            current_fingerprint=str(current_fingerprint),
        )
        force_rebuild_from_earliest = bool(rebuild_outcome.forced)
        planner = self._ingest_window_planner()

        head_time = self._factor_store.head_time(series_id) or 0
        if up_to <= int(head_time):
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

        window_plan = planner.plan_window(
            series_id=series_id,
            up_to=int(up_to),
            head_time=int(head_time),
            tf_s=int(tf_s),
            settings_lookback_candles=int(s.lookback_candles),
            max_window=int(max_window),
            force_rebuild_from_earliest=bool(force_rebuild_from_earliest),
        )
        if window_plan is None:
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

        candle_batch = planner.load_candle_batch(
            series_id=series_id,
            up_to=int(up_to),
            head_time=int(head_time),
            plan=window_plan,
        )
        if candle_batch is None:
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)
        candles = candle_batch.candles
        time_to_idx = candle_batch.time_to_idx
        process_times = candle_batch.process_times

        bootstrap_state = self._build_incremental_bootstrap_state(
            series_id=series_id,
            head_time=int(head_time),
            lookback_candles=int(window_plan.lookback_candles),
            tf_s=int(tf_s),
            state_rebuild_event_limit=int(s.state_rebuild_event_limit),
            candles=candles,
            time_to_idx=time_to_idx,
        )
        effective_pivots = bootstrap_state.effective_pivots
        confirmed_pens = bootstrap_state.confirmed_pens
        zhongshu_state = bootstrap_state.zhongshu_state
        last_major_idx = bootstrap_state.last_major_idx
        anchor_current_ref = bootstrap_state.anchor_current_ref
        anchor_strength = bootstrap_state.anchor_strength
        events: list[FactorEventWrite] = []

        tick_result = self._run_ticks(
            series_id=series_id,
            process_times=process_times,
            tf_s=int(tf_s),
            settings=s,
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
        effective_pivots = tick_result.effective_pivots
        confirmed_pens = tick_result.confirmed_pens
        zhongshu_state = tick_result.zhongshu_state
        anchor_current_ref = tick_result.anchor_current_ref
        anchor_strength = tick_result.anchor_strength
        last_major_idx = tick_result.last_major_idx
        events = tick_result.events

        head_snapshots = self._build_head_snapshots(
            series_id=series_id,
            confirmed_pens=confirmed_pens,
            effective_pivots=effective_pivots,
            zhongshu_state=zhongshu_state,
            anchor_current_ref=anchor_current_ref,
            candles=candles,
            up_to=int(up_to),
        )
        wrote = self._persist_ingest_outputs(
            series_id=series_id,
            up_to=int(up_to),
            events=events,
            head_snapshots=head_snapshots,
            auto_rebuild=auto_rebuild,
            fingerprint=current_fingerprint,
        )

        if self._debug_hub is not None:
            self._debug_hub.emit(
                pipe="write",
                event="write.factor.ingest_done",
                series_id=series_id,
                message="factor ingest done",
                data={
                    "up_to_candle_time": int(up_to),
                    "candles_read": int(len(candles)),
                    "events_planned": int(len(events)),
                    "db_changes": int(wrote),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
        return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)
