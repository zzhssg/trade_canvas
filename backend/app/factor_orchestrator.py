from __future__ import annotations

import os
from dataclasses import dataclass

from .factor_graph import FactorGraph, FactorSpec
from .factor_store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint, build_confirmed_pens_from_major_pivots
from .pivot import compute_major_pivots, compute_minor_pivots_segment
from .store import CandleStore
from .zhongshu import build_dead_zhongshus_from_confirmed_pens


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000


class FactorOrchestrator:
    """
    v0 factor orchestrator:
    - Triggered by closed candles only.
    - Persists minimal factor history:
      - Pivot.major (confirmed, delayed visibility)
      - Pivot.minor (confirmed, delayed visibility; segment-scoped)
      - Pen.confirmed (confirmed pens, delayed by next reverse pivot)
      - Zhongshu.dead (append-only; derived from confirmed pens)
      - Anchor.switch (append-only; stable anchor switches derived from confirmed pens)
    """

    def __init__(self, *, candle_store: CandleStore, factor_store: FactorStore, settings: FactorSettings | None = None) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._settings = settings or FactorSettings()
        self._graph = FactorGraph(
            [
                FactorSpec("pivot", ()),
                FactorSpec("pen", ("pivot",)),
                FactorSpec("zhongshu", ("pen",)),
            ]
        )

    def enabled(self) -> bool:
        raw = os.environ.get("TRADE_CANVAS_ENABLE_FACTOR_INGEST", "1")
        return _truthy_flag(raw)

    def _load_settings(self) -> FactorSettings:
        major_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MAJOR") or "").strip()
        minor_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MINOR") or "").strip()
        lookback_raw = (os.environ.get("TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES") or "").strip()
        major = self._settings.pivot_window_major
        minor = self._settings.pivot_window_minor
        lookback = self._settings.lookback_candles
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
        return FactorSettings(pivot_window_major=int(major), pivot_window_minor=int(minor), lookback_candles=int(lookback))

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        if not self.enabled():
            return

        up_to = int(up_to_candle_time or 0)
        if up_to <= 0:
            return

        s = self._load_settings()
        candles = self._candle_store.get_closed(series_id, since=None, limit=int(s.lookback_candles))
        if not candles:
            return

        candles = [c for c in candles if int(c.candle_time) <= up_to]
        if not candles:
            return

        majors = compute_major_pivots(candles, window=int(s.pivot_window_major))
        major_points: list[PivotMajorPoint] = [
            PivotMajorPoint(
                pivot_time=int(p.pivot_time),
                pivot_price=float(p.pivot_price),
                direction=str(p.direction),
                visible_time=int(p.visible_time),
                pivot_idx=int(p.pivot_idx),
            )
            for p in majors
            if int(p.visible_time) <= up_to
        ]

        pen_confirmed = build_confirmed_pens_from_major_pivots(major_points)
        zhongshu_dead = build_dead_zhongshus_from_confirmed_pens(
            [
                {
                    "start_time": int(p.start_time),
                    "end_time": int(p.end_time),
                    "start_price": float(p.start_price),
                    "end_price": float(p.end_price),
                    "direction": int(p.direction),
                    "visible_time": int(p.visible_time),
                }
                for p in pen_confirmed
            ]
        )

        events: list[FactorEventWrite] = []
        _ = self._graph.topo_order
        for p in major_points:
            key = f"major:{int(p.pivot_time)}:{str(p.direction)}:{int(s.pivot_window_major)}"
            events.append(
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pivot",
                    candle_time=int(p.visible_time),
                    kind="pivot.major",
                    event_key=key,
                    payload={
                        "pivot_time": int(p.pivot_time),
                        "pivot_price": float(p.pivot_price),
                        "direction": str(p.direction),
                        "visible_time": int(p.visible_time),
                        "window": int(s.pivot_window_major),
                        "pivot_idx": int(p.pivot_idx) if p.pivot_idx is not None else None,
                    },
                )
            )

        # pivot.minor as visible event stream (append-only), segmented by last visible major pivot.
        # Segment start idx: last major pivot_idx within the tail candle list.
        segment_start_idx = 0
        last_major_idx: int | None = None
        for p in reversed(major_points):
            if p.pivot_idx is not None:
                last_major_idx = int(p.pivot_idx)
                break
        if last_major_idx is not None:
            segment_start_idx = max(0, int(last_major_idx))

        minors = compute_minor_pivots_segment(
            candles,
            segment_start_idx=int(segment_start_idx),
            window=int(s.pivot_window_minor),
        )
        for m in minors:
            if int(m.visible_time) > up_to:
                continue
            key = f"minor:{int(m.pivot_time)}:{str(m.direction)}:{int(s.pivot_window_minor)}"
            events.append(
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pivot",
                    candle_time=int(m.visible_time),
                    kind="pivot.minor",
                    event_key=key,
                    payload={
                        "pivot_time": int(m.pivot_time),
                        "pivot_price": float(m.pivot_price),
                        "direction": str(m.direction),
                        "visible_time": int(m.visible_time),
                        "window": int(s.pivot_window_minor),
                        "pivot_idx": int(m.pivot_idx),
                    },
                )
            )

        for pen in pen_confirmed:
            if int(pen.visible_time) > up_to:
                continue
            key = f"confirmed:{int(pen.start_time)}:{int(pen.end_time)}:{int(pen.direction)}"
            events.append(
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pen",
                    candle_time=int(pen.visible_time),
                    kind="pen.confirmed",
                    event_key=key,
                    payload={
                        "start_time": int(pen.start_time),
                        "end_time": int(pen.end_time),
                        "start_price": float(pen.start_price),
                        "end_price": float(pen.end_price),
                        "direction": int(pen.direction),
                        "visible_time": int(pen.visible_time),
                        "start_idx": pen.start_idx,
                        "end_idx": pen.end_idx,
                    },
                )
            )

        for zs in zhongshu_dead:
            if int(zs.visible_time) > up_to:
                continue
            key = f"dead:{int(zs.start_time)}:{int(zs.formed_time)}:{int(zs.death_time)}:{zs.zg:.8f}:{zs.zd:.8f}"
            events.append(
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="zhongshu",
                    candle_time=int(zs.visible_time),
                    kind="zhongshu.dead",
                    event_key=key,
                    payload={
                        "start_time": int(zs.start_time),
                        "end_time": int(zs.end_time),
                        "zg": float(zs.zg),
                        "zd": float(zs.zd),
                        "formed_time": int(zs.formed_time),
                        "death_time": int(zs.death_time),
                        "visible_time": int(zs.visible_time),
                    },
                )
            )

        # Anchor switches (stable): choose "strongest confirmed pen so far" and emit a switch when it changes.
        # This is deterministic and append-only (no candidate/head noise).
        best: dict | None = None
        best_strength = -1.0
        for pen in pen_confirmed:
            if int(pen.visible_time) > up_to:
                continue
            strength = abs(float(pen.end_price) - float(pen.start_price))
            if strength <= best_strength:
                continue
            old = best
            best = {
                "kind": "confirmed",
                "start_time": int(pen.start_time),
                "end_time": int(pen.end_time),
                "direction": int(pen.direction),
            }
            best_strength = float(strength)
            key = f"strong_pen:{int(pen.visible_time)}:{best['start_time']}:{best['end_time']}:{best['direction']}"
            events.append(
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="anchor",
                    candle_time=int(pen.visible_time),
                    kind="anchor.switch",
                    event_key=key,
                    payload={
                        "switch_time": int(pen.visible_time),
                        "reason": "strong_pen",
                        "old_anchor": dict(old) if isinstance(old, dict) else None,
                        "new_anchor": dict(best),
                        "visible_time": int(pen.visible_time),
                    },
                )
            )

        with self._factor_store.connect() as conn:
            self._factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=up_to)
            self._factor_store.insert_events_in_conn(conn, events=events)
            conn.commit()
