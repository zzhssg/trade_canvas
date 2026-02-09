from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import pen as pen_module
from . import zhongshu as zhongshu_module
from .debug_hub import DebugHub
from .factor_graph import FactorGraph, FactorSpec
from .factor_processors import AnchorProcessor, PenProcessor, PivotProcessor, ZhongshuProcessor, build_default_factor_processors
from .factor_registry import FactorRegistry
from .factor_semantics import is_more_extreme_pivot
from .factor_slices import build_pen_head_candidate, build_pen_head_preview
from .factor_store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _rebuild_effective_pivots(pivots: list[dict]) -> list[PivotMajorPoint]:
    items: list[PivotMajorPoint] = []
    for p in pivots:
        try:
            items.append(
                PivotMajorPoint(
                    pivot_time=int(p.get("pivot_time") or 0),
                    pivot_price=float(p.get("pivot_price") or 0.0),
                    direction=str(p.get("direction") or ""),
                    visible_time=int(p.get("visible_time") or 0),
                    pivot_idx=int(p.get("pivot_idx")) if p.get("pivot_idx") is not None else None,
                )
            )
        except Exception:
            continue
    items.sort(key=lambda i: (int(i.visible_time), int(i.pivot_time)))

    effective: list[PivotMajorPoint] = []
    for p in items:
        if not effective:
            effective.append(p)
            continue
        last = effective[-1]
        if p.direction == last.direction:
            if is_more_extreme_pivot(last, p):
                effective[-1] = p
            continue
        effective.append(p)
    return effective


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
        self._registry = FactorRegistry(build_default_factor_processors())
        self._pivot_processor = cast(PivotProcessor, self._registry.require("pivot"))
        self._pen_processor = cast(PenProcessor, self._registry.require("pen"))
        self._zhongshu_processor = cast(ZhongshuProcessor, self._registry.require("zhongshu"))
        self._anchor_processor = cast(AnchorProcessor, self._registry.require("anchor"))
        self._graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in self._registry.specs()])

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
            "factor_processors.py": self._file_sha256(Path(__file__).with_name("factor_processors.py")),
            "pen.py": self._file_sha256(Path(getattr(pen_module, "__file__", ""))),
            "zhongshu.py": self._file_sha256(Path(getattr(zhongshu_module, "__file__", ""))),
        }
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

        # Build incremental state from recent history.
        state_start = max(0, int(head_time) - int(lookback_candles) * int(tf_s))
        state_scan_limit = max(int(s.state_rebuild_event_limit), int(lookback_candles) * 8)
        rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(state_start),
            end_candle_time=int(head_time),
            limit=int(state_scan_limit),
        )
        if len(rows) >= int(state_scan_limit) and self._debug_hub is not None:
            self._debug_hub.emit(
                pipe="write",
                event="factor.state_rebuild.limit_reached",
                series_id=series_id,
                message="state rebuild event scan reached limit; consider raising TRADE_CANVAS_FACTOR_STATE_REBUILD_EVENT_LIMIT",
                data={
                    "state_start": int(state_start),
                    "head_time": int(head_time),
                    "scan_limit": int(state_scan_limit),
                    "rows": int(len(rows)),
                },
            )

        pivot_events: list[dict] = []
        pen_events: list[dict] = []
        anchor_switches: list[dict] = []
        for r in rows:
            if r.factor_name == "pivot" and r.kind == "pivot.major":
                pivot_events.append(dict(r.payload or {}))
            elif r.factor_name == "pen" and r.kind == "pen.confirmed":
                pen_events.append(dict(r.payload or {}))
            elif r.factor_name == "anchor" and r.kind == "anchor.switch":
                anchor_switches.append(dict(r.payload or {}))

        pivot_events.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("pivot_time", 0))))
        pen_events.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("start_time", 0))))
        anchor_switches.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("switch_time", 0))))

        effective_pivots = _rebuild_effective_pivots(pivot_events)
        confirmed_pens: list[dict] = list(pen_events)
        candles_up_to_head = [c for c in candles if int(c.candle_time) <= int(head_time)]
        zhongshu_state = self._zhongshu_processor.build_state(
            confirmed_pens=confirmed_pens,
            candles_up_to_head=candles_up_to_head,
            head_time=int(head_time),
        )

        last_major_idx: int | None = None
        if effective_pivots:
            last = effective_pivots[-1]
            if last.pivot_idx is not None:
                last_major_idx = int(last.pivot_idx)
            else:
                last_major_idx = time_to_idx.get(int(last.pivot_time))

        anchor_current_ref, anchor_strength = self._anchor_processor.restore_anchor_state(
            anchor_switches=anchor_switches,
            confirmed_pens=confirmed_pens,
            candles=candles,
        )

        events: list[FactorEventWrite] = []

        for visible_time in process_times:
            best_strong_pen_ref: dict[str, int | str] | None = None
            best_strong_pen_strength: float | None = None
            baseline_anchor_strength = float(anchor_strength) if anchor_strength is not None else None
            pivot_time_major = int(visible_time) - int(s.pivot_window_major) * int(tf_s)
            major_candidates = self._pivot_processor.compute_major_candidates(
                candles=candles,
                time_to_idx=time_to_idx,
                pivot_time=int(pivot_time_major),
                visible_time=int(visible_time),
                window=int(s.pivot_window_major),
            )
            major_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))

            for p in major_candidates:
                events.append(
                    self._pivot_processor.build_major_event(
                        series_id=series_id,
                        pivot=p,
                        window=int(s.pivot_window_major),
                    )
                )

                last_major_idx = int(p.pivot_idx) if p.pivot_idx is not None else last_major_idx

                confirmed = self._pen_processor.append_pivot_and_confirm(effective_pivots, p)
                for pen in confirmed:
                    pen_event = self._pen_processor.build_confirmed_event(series_id=series_id, pen=pen)
                    pen_payload = dict(pen_event.payload)
                    events.append(pen_event)
                    confirmed_pens.append(pen_payload)

                    dead_event, formed_entry = self._zhongshu_processor.update_state_from_pen(
                        state=zhongshu_state,
                        series_id=series_id,
                        pen_payload=pen_payload,
                    )
                    if dead_event is not None:
                        events.append(dead_event)

                    if formed_entry is not None:
                        switch_event, anchor_current_ref, anchor_strength = self._anchor_processor.apply_zhongshu_entry_switch(
                            series_id=series_id,
                            formed_entry=formed_entry,
                            switch_time=int(visible_time),
                            old_anchor=anchor_current_ref,
                        )
                        if switch_event is not None:
                            events.append(switch_event)

                    # strong_pen candidate on confirmed pen (defer event emission until this visible_time is fully processed).
                    best_strong_pen_ref, best_strong_pen_strength = self._anchor_processor.maybe_pick_stronger_pen(
                        candidate_pen=pen_payload,
                        kind="confirmed",
                        baseline_anchor_strength=baseline_anchor_strength,
                        current_best_ref=best_strong_pen_ref,
                        current_best_strength=best_strong_pen_strength,
                    )
            pivot_time_minor = int(visible_time) - int(s.pivot_window_minor) * int(tf_s)
            minor_candidates = self._pivot_processor.compute_minor_candidates(
                candles=candles,
                time_to_idx=time_to_idx,
                pivot_time=int(pivot_time_minor),
                visible_time=int(visible_time),
                window=int(s.pivot_window_minor),
                segment_start_idx=last_major_idx,
            )
            minor_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))
            for m in minor_candidates:
                events.append(
                    self._pivot_processor.build_minor_event(
                        series_id=series_id,
                        pivot=m,
                        window=int(s.pivot_window_minor),
                    )
                )

            idx_now = time_to_idx.get(int(visible_time))
            if idx_now is not None:
                c = candles[int(idx_now)]
                formed_entry_on_candle = self._zhongshu_processor.update_state_from_closed_candle(
                    state=zhongshu_state,
                    candle_time=int(c.candle_time),
                    high=float(c.high),
                    low=float(c.low),
                )
                if formed_entry_on_candle is not None:
                    switch_event, anchor_current_ref, anchor_strength = self._anchor_processor.apply_zhongshu_entry_switch(
                        series_id=series_id,
                        formed_entry=formed_entry_on_candle,
                        switch_time=int(visible_time),
                        old_anchor=anchor_current_ref,
                    )
                    if switch_event is not None:
                        events.append(switch_event)

            # strong_pen candidate on candidate pen (head), merged with confirmed candidates by max strength.
            last_pen = confirmed_pens[-1] if confirmed_pens else None
            candidate = build_pen_head_candidate(candles=candles, last_confirmed=last_pen, aligned_time=int(visible_time))
            if candidate is not None:
                best_strong_pen_ref, best_strong_pen_strength = self._anchor_processor.maybe_pick_stronger_pen(
                    candidate_pen=candidate,
                    kind="candidate",
                    baseline_anchor_strength=baseline_anchor_strength,
                    current_best_ref=best_strong_pen_ref,
                    current_best_strength=best_strong_pen_strength,
                )

            if best_strong_pen_ref is not None and best_strong_pen_strength is not None:
                switch_event, anchor_current_ref, anchor_strength = self._anchor_processor.apply_strong_pen_switch(
                    series_id=series_id,
                    switch_time=int(visible_time),
                    old_anchor=anchor_current_ref,
                    new_anchor=best_strong_pen_ref,
                    new_anchor_strength=float(best_strong_pen_strength),
                )
                if switch_event is not None:
                    events.append(switch_event)

        # Head snapshots (append-only via seq).
        pen_head: dict[str, Any] = {}
        if confirmed_pens:
            major_for_head = [
                {
                    "pivot_time": int(p.pivot_time),
                    "pivot_price": float(p.pivot_price),
                    "direction": str(p.direction),
                    "visible_time": int(p.visible_time),
                }
                for p in effective_pivots
            ]
            preview = build_pen_head_preview(candles=candles, major_pivots=major_for_head, aligned_time=int(up_to))
            for key in ("extending", "candidate"):
                v = preview.get(key)
                if isinstance(v, dict):
                    pen_head[key] = v

        zhongshu_head = self._zhongshu_processor.build_alive_head(
            state=zhongshu_state,
            confirmed_pens=confirmed_pens,
            up_to_visible_time=int(up_to),
            candles=candles,
        )

        anchor_head: dict[str, Any] = {}
        if confirmed_pens or anchor_current_ref is not None:
            anchor_head = {"current_anchor_ref": anchor_current_ref}

        with self._factor_store.connect() as conn:
            before_changes = int(conn.total_changes)
            self._factor_store.insert_events_in_conn(conn, events=events)
            if confirmed_pens:
                self._factor_store.insert_head_snapshot_in_conn(
                    conn,
                    series_id=series_id,
                    factor_name="pen",
                    candle_time=int(up_to),
                    head=pen_head,
                )
            if "alive" in zhongshu_head:
                self._factor_store.insert_head_snapshot_in_conn(
                    conn,
                    series_id=series_id,
                    factor_name="zhongshu",
                    candle_time=int(up_to),
                    head=zhongshu_head,
                )
            if anchor_head:
                self._factor_store.insert_head_snapshot_in_conn(
                    conn,
                    series_id=series_id,
                    factor_name="anchor",
                    candle_time=int(up_to),
                    head=anchor_head,
                )
            self._factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(up_to))
            if auto_rebuild:
                self._factor_store.upsert_series_fingerprint_in_conn(
                    conn,
                    series_id=series_id,
                    fingerprint=current_fingerprint,
                )
            conn.commit()
            wrote = int(conn.total_changes) - before_changes

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
