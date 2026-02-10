from __future__ import annotations

import hashlib
import inspect
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, cast

from . import pen as pen_module
from . import zhongshu as zhongshu_module
from .debug_hub import DebugHub
from .factor_graph import FactorGraph, FactorSpec
from .factor_manifest import build_default_factor_manifest
from .factor_processors import AnchorProcessor
from .factor_registry import FactorRegistry
from .factor_store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000
    state_rebuild_event_limit: int = 50000


@dataclass(frozen=True)
class FactorIngestResult:
    rebuilt: bool = False
    fingerprint: str | None = None


@dataclass
class _FactorTickState:
    visible_time: int
    tf_s: int
    settings: FactorSettings
    candles: list[Any]
    time_to_idx: dict[int, int]
    events: list[FactorEventWrite]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    last_major_idx: int | None
    major_candidates: list[PivotMajorPoint]
    new_confirmed_pen_payloads: list[dict[str, Any]]
    formed_entries: list[dict[str, Any]]
    best_strong_pen_ref: dict[str, int | str] | None
    best_strong_pen_strength: float | None
    baseline_anchor_strength: float | None


@dataclass(frozen=True)
class _RebuildEventBuckets:
    events_by_factor: dict[str, list[dict[str, Any]]]
    rows_count: int
    rows_truncated: bool


@dataclass
class _HeadBuildState:
    up_to: int
    candles: list[Any]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None


@dataclass(frozen=True)
class _BootstrapState:
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    last_major_idx: int | None
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None


@dataclass
class _BootstrapReplayState:
    head_time: int
    candles: list[Any]
    time_to_idx: dict[int, int]
    rebuild_events: dict[str, list[dict[str, Any]]]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    last_major_idx: int | None
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None


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

    def __init__(self, *, candle_store: CandleStore, factor_store: FactorStore, settings: FactorSettings | None = None) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._settings = settings or FactorSettings()
        self._debug_hub: DebugHub | None = None
        manifest = build_default_factor_manifest()
        self._registry = FactorRegistry(list(manifest.processors))
        self._anchor_processor = cast(AnchorProcessor, self._registry.require("anchor"))
        self._graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in self._registry.specs()])
        self._tick_runtime: dict[str, Any] = {
            "anchor_processor": self._anchor_processor,
        }

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

    def _fingerprint_rebuild_enabled(self) -> bool:
        raw = os.environ.get("TRADE_CANVAS_ENABLE_FACTOR_FINGERPRINT_REBUILD", "1")
        return _truthy_flag(raw)

    def _file_sha256(self, path: Path) -> str:
        try:
            data = path.read_bytes()
        except Exception:
            return "missing"
        return hashlib.sha256(data).hexdigest()

    def _build_series_fingerprint(self, *, series_id: str, settings: FactorSettings) -> str:
        files = {
            "factor_orchestrator.py": self._file_sha256(Path(__file__)),
            "factor_manifest.py": self._file_sha256(Path(__file__).with_name("factor_manifest.py")),
            "factor_plugin_contract.py": self._file_sha256(Path(__file__).with_name("factor_plugin_contract.py")),
            "factor_plugin_registry.py": self._file_sha256(Path(__file__).with_name("factor_plugin_registry.py")),
            "pen.py": self._file_sha256(Path(getattr(pen_module, "__file__", ""))),
            "zhongshu.py": self._file_sha256(Path(getattr(zhongshu_module, "__file__", ""))),
        }
        for plugin in sorted(self._registry.plugins(), key=lambda p: str(p.spec.factor_name)):
            try:
                plugin_file = Path(inspect.getfile(plugin.__class__))
            except Exception:
                continue
            files[f"plugin:{plugin.spec.factor_name}"] = self._file_sha256(plugin_file)
        payload = {
            "series_id": str(series_id),
            "graph": list(self._graph.topo_order),
            "settings": {
                "pivot_window_major": int(settings.pivot_window_major),
                "pivot_window_minor": int(settings.pivot_window_minor),
                "lookback_candles": int(settings.lookback_candles),
                "state_rebuild_event_limit": int(settings.state_rebuild_event_limit),
            },
            "files": files,
            "logic_version_override": str(os.environ.get("TRADE_CANVAS_FACTOR_LOGIC_VERSION") or ""),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def enabled(self) -> bool:
        raw = os.environ.get("TRADE_CANVAS_ENABLE_FACTOR_INGEST", "1")
        return _truthy_flag(raw)

    def _load_settings(self) -> FactorSettings:
        major_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MAJOR") or "").strip()
        minor_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MINOR") or "").strip()
        lookback_raw = (os.environ.get("TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES") or "").strip()
        state_limit_raw = (os.environ.get("TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT") or "").strip()
        major = self._settings.pivot_window_major
        minor = self._settings.pivot_window_minor
        lookback = self._settings.lookback_candles
        state_limit = self._settings.state_rebuild_event_limit
        if major_raw:
            try:
                major = max(1, int(major_raw))
            except ValueError:
                major = self._settings.pivot_window_major
        if minor_raw:
            try:
                minor = max(1, int(minor_raw))
            except ValueError:
                minor = self._settings.pivot_window_minor
        if lookback_raw:
            try:
                lookback = max(100, int(lookback_raw))
            except ValueError:
                lookback = self._settings.lookback_candles
        if state_limit_raw:
            try:
                state_limit = max(1000, int(state_limit_raw))
            except ValueError:
                state_limit = self._settings.state_rebuild_event_limit
        return FactorSettings(
            pivot_window_major=int(major),
            pivot_window_minor=int(minor),
            lookback_candles=int(lookback),
            state_rebuild_event_limit=int(state_limit),
        )

    def _run_tick_steps(self, *, series_id: str, state: _FactorTickState) -> None:
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            run_tick = getattr(plugin, "run_tick", None)
            if not callable(run_tick):
                raise RuntimeError(f"factor_missing_run_tick:{factor_name}")
            run_tick(series_id=series_id, state=state, runtime=self._tick_runtime)

    def _bucket_rebuild_event_row(
        self,
        row: Any,
        *,
        events_by_factor: dict[str, list[dict[str, Any]]],
    ) -> None:
        factor_name = str(row.factor_name or "")
        plugin = self._registry.get(factor_name)
        if plugin is None:
            return
        collector = getattr(plugin, "collect_rebuild_event", None)
        if not callable(collector):
            return
        collector(
            kind=str(row.kind),
            payload=dict(row.payload or {}),
            events=events_by_factor.setdefault(factor_name, []),
        )

    def _emit_rebuild_limit_reached(
        self,
        *,
        series_id: str,
        state_start: int,
        head_time: int,
        scan_limit: int,
        rows_count: int,
    ) -> None:
        if self._debug_hub is None:
            return
        self._debug_hub.emit(
            pipe="write",
            event="factor.state_rebuild.limit_reached",
            series_id=series_id,
            message="state rebuild event scan reached limit; switched to paged full scan",
            data={
                "state_start": int(state_start),
                "head_time": int(head_time),
                "scan_limit": int(scan_limit),
                "rows": int(rows_count),
                "mode": "paged_full_scan",
            },
        )

    def _collect_rebuild_event_buckets(
        self,
        *,
        series_id: str,
        state_start: int,
        head_time: int,
        scan_limit: int,
    ) -> _RebuildEventBuckets:
        rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(state_start),
            end_candle_time=int(head_time),
            limit=int(scan_limit),
        )
        rows_truncated = len(rows) >= int(scan_limit)
        row_iter: Iterable[Any]
        if rows_truncated:
            row_iter = self._factor_store.iter_events_between_times_paged(
                series_id=series_id,
                factor_name=None,
                start_candle_time=int(state_start),
                end_candle_time=int(head_time),
                page_size=int(scan_limit),
            )
        else:
            row_iter = rows

        events_by_factor: dict[str, list[dict[str, Any]]] = {
            str(factor_name): [] for factor_name in self._graph.topo_order
        }
        rows_count = 0

        for row in row_iter:
            rows_count += 1
            self._bucket_rebuild_event_row(
                row,
                events_by_factor=events_by_factor,
            )

        if rows_truncated:
            self._emit_rebuild_limit_reached(
                series_id=series_id,
                state_start=int(state_start),
                head_time=int(head_time),
                scan_limit=int(scan_limit),
                rows_count=int(rows_count),
            )

        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            sorter = getattr(plugin, "sort_rebuild_events", None)
            events = events_by_factor.setdefault(str(factor_name), [])
            if callable(sorter):
                sorter(events=events)

        return _RebuildEventBuckets(
            events_by_factor=events_by_factor,
            rows_count=int(rows_count),
            rows_truncated=bool(rows_truncated),
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
    ) -> _BootstrapState:
        state_start = max(0, int(head_time) - int(lookback_candles) * int(tf_s))
        state_scan_limit = max(int(state_rebuild_event_limit), int(lookback_candles) * 8)
        rebuild_events = self._collect_rebuild_event_buckets(
            series_id=series_id,
            state_start=int(state_start),
            head_time=int(head_time),
            scan_limit=int(state_scan_limit),
        )
        state = _BootstrapReplayState(
            head_time=int(head_time),
            candles=candles,
            time_to_idx=time_to_idx,
            rebuild_events=rebuild_events.events_by_factor,
            effective_pivots=[],
            confirmed_pens=[],
            zhongshu_state={},
            last_major_idx=None,
            anchor_current_ref=None,
            anchor_strength=None,
        )
        for factor_name in self._graph.topo_order:
            plugin = self._registry.require(str(factor_name))
            bootstrap = getattr(plugin, "bootstrap_from_history", None)
            if not callable(bootstrap):
                continue
            bootstrap(series_id=series_id, state=state, runtime=self._tick_runtime)
        return _BootstrapState(
            effective_pivots=state.effective_pivots,
            confirmed_pens=state.confirmed_pens,
            zhongshu_state=state.zhongshu_state,
            last_major_idx=state.last_major_idx,
            anchor_current_ref=state.anchor_current_ref,
            anchor_strength=state.anchor_strength,
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
        force_rebuild_from_earliest = False

        if auto_rebuild:
            current = self._factor_store.get_series_fingerprint(series_id)
            if current is None or str(current.fingerprint) != str(current_fingerprint):
                keep_raw = (os.environ.get("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES") or "").strip()
                try:
                    keep_candles = max(100, int(keep_raw)) if keep_raw else 2000
                except ValueError:
                    keep_candles = 2000
                trimmed_rows = 0
                with self._candle_store.connect() as conn:
                    trimmed_rows = self._candle_store.trim_series_to_latest_n_in_conn(
                        conn,
                        series_id=series_id,
                        keep=int(keep_candles),
                    )
                    conn.commit()
                with self._factor_store.connect() as conn:
                    self._factor_store.clear_series_in_conn(conn, series_id=series_id)
                    self._factor_store.upsert_series_fingerprint_in_conn(
                        conn,
                        series_id=series_id,
                        fingerprint=current_fingerprint,
                    )
                    conn.commit()
                force_rebuild_from_earliest = True
                if self._debug_hub is not None:
                    self._debug_hub.emit(
                        pipe="write",
                        event="factor.fingerprint.rebuild",
                        message="fingerprint mismatch, cleared factor data and rebuilding from latest 2000 candles",
                        series_id=series_id,
                        data={
                            "series_id": str(series_id),
                            "fingerprint": str(current_fingerprint),
                            "keep_candles": int(keep_candles),
                            "trimmed_rows": int(trimmed_rows),
                        },
                    )

        head_time = self._factor_store.head_time(series_id) or 0
        if up_to <= int(head_time):
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

        lookback_candles = int(s.lookback_candles) + int(max_window) * 2 + 5
        if force_rebuild_from_earliest:
            earliest = self._candle_store.first_time(series_id)
            if earliest is None:
                return FactorIngestResult(rebuilt=True, fingerprint=current_fingerprint)
            start_time = int(earliest)
            total = self._candle_store.count_closed_between_times(
                series_id,
                start_time=int(start_time),
                end_time=int(up_to),
            )
            read_limit = max(int(total) + 10, int(lookback_candles) + 10)
        else:
            start_time = max(0, int(up_to) - int(lookback_candles) * int(tf_s))
            if head_time > 0:
                start_time = max(0, min(int(start_time), int(head_time) - int(max_window) * 2 * int(tf_s)))
            read_limit = int(lookback_candles) + 10

        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(up_to),
            limit=int(read_limit),
        )
        if not candles:
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

        candle_times = [int(c.candle_time) for c in candles]
        time_to_idx = {int(t): int(i) for i, t in enumerate(candle_times)}
        process_times = [t for t in candle_times if int(t) > int(head_time) and int(t) <= int(up_to)]
        if not process_times:
            return FactorIngestResult(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

        bootstrap_state = self._build_incremental_bootstrap_state(
            series_id=series_id,
            head_time=int(head_time),
            lookback_candles=int(lookback_candles),
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

        for visible_time in process_times:
            tick_state = _FactorTickState(
                visible_time=int(visible_time),
                tf_s=int(tf_s),
                settings=s,
                candles=candles,
                time_to_idx=time_to_idx,
                events=events,
                effective_pivots=effective_pivots,
                confirmed_pens=confirmed_pens,
                zhongshu_state=zhongshu_state,
                anchor_current_ref=anchor_current_ref,
                anchor_strength=anchor_strength,
                last_major_idx=last_major_idx,
                major_candidates=[],
                new_confirmed_pen_payloads=[],
                formed_entries=[],
                best_strong_pen_ref=None,
                best_strong_pen_strength=None,
                baseline_anchor_strength=float(anchor_strength) if anchor_strength is not None else None,
            )
            self._run_tick_steps(series_id=series_id, state=tick_state)
            anchor_current_ref = tick_state.anchor_current_ref
            anchor_strength = tick_state.anchor_strength
            last_major_idx = tick_state.last_major_idx

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
