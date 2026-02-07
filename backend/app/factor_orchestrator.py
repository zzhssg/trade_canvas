from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from .anchor_semantics import should_append_switch
from .debug_hub import DebugHub
from .factor_graph import FactorGraph, FactorSpec
from .factor_slices import build_pen_head_candidate
from .factor_store import FactorEventWrite, FactorStore
from .pen import ConfirmedPen, PivotMajorPoint
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .zhongshu import ZhongshuDead, build_alive_zhongshu_from_confirmed_pens


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _is_more_extreme(prev: PivotMajorPoint, cur: PivotMajorPoint) -> bool:
    if cur.direction != prev.direction:
        return False
    if cur.direction == "resistance":
        return float(cur.pivot_price) > float(prev.pivot_price)
    return float(cur.pivot_price) < float(prev.pivot_price)


def _pen_strength(pen: dict) -> float:
    try:
        return abs(float(pen.get("end_price") or 0.0) - float(pen.get("start_price") or 0.0))
    except Exception:
        return -1.0


def _pen_ref_from_pen(pen: dict, *, kind: str) -> dict:
    return {
        "kind": kind,
        "start_time": int(pen.get("start_time") or 0),
        "end_time": int(pen.get("end_time") or 0),
        "direction": int(pen.get("direction") or 0),
    }


def _as_range(pen: dict) -> tuple[float, float] | None:
    try:
        a = float(pen.get("start_price"))
        b = float(pen.get("end_price"))
    except Exception:
        return None
    lo = a if a <= b else b
    hi = b if a <= b else a
    return (lo, hi)


def _try_form_zhongshu(window: list[dict]) -> dict | None:
    if len(window) < 3:
        return None
    ranges = [_as_range(p) for p in window[-3:]]
    if any(r is None for r in ranges):
        return None
    lo = max(r[0] for r in ranges if r is not None)
    hi = min(r[1] for r in ranges if r is not None)
    if lo > hi:
        return None
    third = window[-1]
    formed_time = int(third.get("visible_time") or 0)
    if formed_time <= 0:
        return None
    start_time = int(window[-3].get("start_time") or 0)
    end_time = int(third.get("end_time") or 0)
    if start_time <= 0 or end_time <= 0:
        return None
    return {
        "start_time": start_time,
        "end_time": end_time,
        "zg": float(hi),
        "zd": float(lo),
        "formed_time": formed_time,
        "last_seen_visible_time": formed_time,
    }


def _update_zhongshu_state(state: dict, pen: dict) -> tuple[ZhongshuDead | None, dict | None]:
    tail: list[dict] = list(state.get("tail") or [])
    tail.append(pen)
    if len(tail) > 3:
        tail = tail[-3:]

    alive = state.get("alive")
    formed_entry_pen: dict | None = None
    dead_event: ZhongshuDead | None = None

    r = _as_range(pen)
    if r is None:
        state["tail"] = tail
        return None, None

    if alive is None:
        alive = _try_form_zhongshu(tail)
        if alive is not None:
            formed_entry_pen = tail[0]
    else:
        lo = float(alive["zd"])
        hi = float(alive["zg"])
        nlo = max(lo, float(r[0]))
        nhi = min(hi, float(r[1]))
        if nlo <= nhi:
            alive["zd"] = float(nlo)
            alive["zg"] = float(nhi)
            try:
                alive["end_time"] = max(int(alive.get("end_time") or 0), int(pen.get("end_time") or 0))
            except Exception:
                pass
            alive["last_seen_visible_time"] = int(pen.get("visible_time") or 0)
        else:
            visible_time = int(pen.get("visible_time") or 0)
            dead_event = ZhongshuDead(
                start_time=int(alive["start_time"]),
                end_time=int(alive.get("end_time") or 0),
                zg=float(alive["zg"]),
                zd=float(alive["zd"]),
                formed_time=int(alive["formed_time"]),
                death_time=int(visible_time),
                visible_time=int(visible_time),
            )
            alive = _try_form_zhongshu(tail)
            if alive is not None:
                formed_entry_pen = tail[0]

    state["alive"] = alive
    state["tail"] = tail
    return dead_event, formed_entry_pen


def _replay_zhongshu_state(pens: list[dict]) -> dict:
    state: dict[str, Any] = {"alive": None, "tail": []}
    for pen in pens:
        _update_zhongshu_state(state, pen)
    return state


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
            if _is_more_extreme(last, p):
                effective[-1] = p
            continue
        effective.append(p)
    return effective


def _append_pivot_and_confirm(effective: list[PivotMajorPoint], new_pivot: PivotMajorPoint) -> list[ConfirmedPen]:
    if not effective:
        effective.append(new_pivot)
        return []

    last = effective[-1]
    if new_pivot.direction == last.direction:
        if _is_more_extreme(last, new_pivot):
            effective[-1] = new_pivot
        return []

    effective.append(new_pivot)
    if len(effective) < 3:
        return []

    p0 = effective[-3]
    p1 = effective[-2]
    confirmer = effective[-1]
    direction = 1 if float(p1.pivot_price) > float(p0.pivot_price) else -1
    return [
        ConfirmedPen(
            start_time=int(p0.pivot_time),
            end_time=int(p1.pivot_time),
            start_price=float(p0.pivot_price),
            end_price=float(p1.pivot_price),
            direction=int(direction),
            visible_time=int(confirmer.visible_time),
            start_idx=p0.pivot_idx,
            end_idx=p1.pivot_idx,
        )
    ]


def _compute_major_candidates(
    *,
    candles: list[Any],
    time_to_idx: dict[int, int],
    pivot_time: int,
    visible_time: int,
    window: int,
) -> list[PivotMajorPoint]:
    idx = time_to_idx.get(int(pivot_time))
    if idx is None:
        return []
    w = int(window)
    if idx - w < 0 or idx + w >= len(candles):
        return []
    if int(candles[idx + w].candle_time) != int(visible_time):
        return []

    target_high = float(candles[idx].high)
    is_max_left = all(float(candles[i].high) < target_high for i in range(idx - w, idx))
    is_max_right = all(float(candles[i].high) <= target_high for i in range(idx + 1, idx + w + 1))

    target_low = float(candles[idx].low)
    is_min_left = all(float(candles[i].low) > target_low for i in range(idx - w, idx))
    is_min_right = all(float(candles[i].low) >= target_low for i in range(idx + 1, idx + w + 1))

    out: list[PivotMajorPoint] = []
    if is_max_left and is_max_right:
        out.append(
            PivotMajorPoint(
                pivot_time=int(pivot_time),
                pivot_price=float(target_high),
                direction="resistance",
                visible_time=int(visible_time),
                pivot_idx=int(idx),
            )
        )
    if is_min_left and is_min_right:
        out.append(
            PivotMajorPoint(
                pivot_time=int(pivot_time),
                pivot_price=float(target_low),
                direction="support",
                visible_time=int(visible_time),
                pivot_idx=int(idx),
            )
        )
    return out


def _compute_minor_candidates(
    *,
    candles: list[Any],
    time_to_idx: dict[int, int],
    pivot_time: int,
    visible_time: int,
    window: int,
    segment_start_idx: int | None,
) -> list[PivotMajorPoint]:
    if segment_start_idx is None:
        return []
    idx = time_to_idx.get(int(pivot_time))
    if idx is None:
        return []
    w = int(window)
    if idx - w < 0 or idx + w >= len(candles):
        return []
    if idx - w < int(segment_start_idx):
        return []
    if int(candles[idx + w].candle_time) != int(visible_time):
        return []

    highs = [float(candles[i].high) for i in range(idx - w, idx + w + 1)]
    lows = [float(candles[i].low) for i in range(idx - w, idx + w + 1)]
    max_high = max(highs) if highs else None
    min_low = min(lows) if lows else None
    if max_high is None or min_low is None:
        return []

    center_high = float(candles[idx].high)
    center_low = float(candles[idx].low)

    out: list[PivotMajorPoint] = []
    if center_high >= float(max_high):
        out.append(
            PivotMajorPoint(
                pivot_time=int(pivot_time),
                pivot_price=float(center_high),
                direction="resistance",
                visible_time=int(visible_time),
                pivot_idx=int(idx),
            )
        )
    if center_low <= float(min_low):
        out.append(
            PivotMajorPoint(
                pivot_time=int(pivot_time),
                pivot_price=float(center_low),
                direction="support",
                visible_time=int(visible_time),
                pivot_idx=int(idx),
            )
        )
    return out


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000


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
        self._graph = FactorGraph(
            [
                FactorSpec("pivot", ()),
                FactorSpec("pen", ("pivot",)),
                FactorSpec("zhongshu", ("pen",)),
                FactorSpec("anchor", ("pen", "zhongshu")),
            ]
        )

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

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
        t0 = time.perf_counter()
        if not self.enabled():
            return

        up_to = int(up_to_candle_time or 0)
        if up_to <= 0:
            return

        s = self._load_settings()
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        max_window = max(int(s.pivot_window_major), int(s.pivot_window_minor))

        head_time = self._factor_store.head_time(series_id) or 0
        if up_to <= int(head_time):
            return

        lookback_candles = int(s.lookback_candles) + int(max_window) * 2 + 5
        start_time = max(0, int(up_to) - int(lookback_candles) * int(tf_s))
        if head_time > 0:
            start_time = max(0, min(int(start_time), int(head_time) - int(max_window) * 2 * int(tf_s)))

        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(up_to),
            limit=int(lookback_candles) + 10,
        )
        if not candles:
            return

        candle_times = [int(c.candle_time) for c in candles]
        time_to_idx = {int(t): int(i) for i, t in enumerate(candle_times)}
        process_times = [t for t in candle_times if int(t) > int(head_time) and int(t) <= int(up_to)]
        if not process_times:
            return

        # Build incremental state from recent history.
        state_start = max(0, int(head_time) - int(lookback_candles) * int(tf_s))
        rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(state_start),
            end_candle_time=int(head_time),
            limit=50000,
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
        zhongshu_state = _replay_zhongshu_state(confirmed_pens)

        last_major_idx: int | None = None
        if effective_pivots:
            last = effective_pivots[-1]
            if last.pivot_idx is not None:
                last_major_idx = int(last.pivot_idx)
            else:
                last_major_idx = time_to_idx.get(int(last.pivot_time))

        anchor_current_ref: dict | None = None
        anchor_strength: float | None = None
        if anchor_switches:
            last_switch = anchor_switches[-1]
            cur = last_switch.get("new_anchor")
            if isinstance(cur, dict):
                anchor_current_ref = cur
                kind = str(cur.get("kind") or "")
                if kind == "confirmed":
                    match = next(
                        (
                            p
                            for p in reversed(confirmed_pens)
                            if int(p.get("start_time") or 0) == int(cur.get("start_time") or 0)
                            and int(p.get("end_time") or 0) == int(cur.get("end_time") or 0)
                            and int(p.get("direction") or 0) == int(cur.get("direction") or 0)
                        ),
                        None,
                    )
                    if match is not None:
                        anchor_strength = _pen_strength(match)
                elif kind == "candidate":
                    switch_time = int(last_switch.get("switch_time") or 0)
                    if switch_time > 0:
                        pen_at_time = [p for p in confirmed_pens if int(p.get("visible_time") or 0) <= switch_time]
                        last_pen = pen_at_time[-1] if pen_at_time else None
                        candidate = build_pen_head_candidate(candles=candles, last_confirmed=last_pen, aligned_time=int(switch_time))
                        if candidate is not None:
                            anchor_strength = _pen_strength(candidate)

        if anchor_current_ref is None and confirmed_pens:
            last = confirmed_pens[-1]
            anchor_current_ref = _pen_ref_from_pen(last, kind="confirmed")
            anchor_strength = _pen_strength(last)

        events: list[FactorEventWrite] = []
        _ = self._graph.topo_order

        for visible_time in process_times:
            pivot_time_major = int(visible_time) - int(s.pivot_window_major) * int(tf_s)
            major_candidates = _compute_major_candidates(
                candles=candles,
                time_to_idx=time_to_idx,
                pivot_time=int(pivot_time_major),
                visible_time=int(visible_time),
                window=int(s.pivot_window_major),
            )
            major_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))

            for p in major_candidates:
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

                last_major_idx = int(p.pivot_idx) if p.pivot_idx is not None else last_major_idx

                confirmed = _append_pivot_and_confirm(effective_pivots, p)
                for pen in confirmed:
                    key_pen = f"confirmed:{int(pen.start_time)}:{int(pen.end_time)}:{int(pen.direction)}"
                    pen_payload = {
                        "start_time": int(pen.start_time),
                        "end_time": int(pen.end_time),
                        "start_price": float(pen.start_price),
                        "end_price": float(pen.end_price),
                        "direction": int(pen.direction),
                        "visible_time": int(pen.visible_time),
                        "start_idx": pen.start_idx,
                        "end_idx": pen.end_idx,
                    }
                    events.append(
                        FactorEventWrite(
                            series_id=series_id,
                            factor_name="pen",
                            candle_time=int(pen.visible_time),
                            kind="pen.confirmed",
                            event_key=key_pen,
                            payload=pen_payload,
                        )
                    )
                    confirmed_pens.append(pen_payload)

                    dead_event, formed_entry = _update_zhongshu_state(zhongshu_state, pen_payload)
                    if dead_event is not None:
                        key_dead = (
                            f"dead:{int(dead_event.start_time)}:{int(dead_event.formed_time)}:{int(dead_event.death_time)}:"
                            f"{float(dead_event.zg):.8f}:{float(dead_event.zd):.8f}"
                        )
                        events.append(
                            FactorEventWrite(
                                series_id=series_id,
                                factor_name="zhongshu",
                                candle_time=int(dead_event.visible_time),
                                kind="zhongshu.dead",
                                event_key=key_dead,
                                payload={
                                    "start_time": int(dead_event.start_time),
                                    "end_time": int(dead_event.end_time),
                                    "zg": float(dead_event.zg),
                                    "zd": float(dead_event.zd),
                                    "formed_time": int(dead_event.formed_time),
                                    "death_time": int(dead_event.death_time),
                                    "visible_time": int(dead_event.visible_time),
                                },
                            )
                        )

                    if formed_entry is not None:
                        new_ref = _pen_ref_from_pen(formed_entry, kind="confirmed")
                        if should_append_switch(old_anchor=anchor_current_ref, new_anchor=new_ref):
                            key_switch = (
                                f"zhongshu_entry:{int(visible_time)}:{new_ref['start_time']}:{new_ref['end_time']}:{new_ref['direction']}"
                            )
                            events.append(
                                FactorEventWrite(
                                    series_id=series_id,
                                    factor_name="anchor",
                                    candle_time=int(visible_time),
                                    kind="anchor.switch",
                                    event_key=key_switch,
                                    payload={
                                        "switch_time": int(visible_time),
                                        "reason": "zhongshu_entry",
                                        "old_anchor": dict(anchor_current_ref) if isinstance(anchor_current_ref, dict) else None,
                                        "new_anchor": dict(new_ref),
                                        "visible_time": int(visible_time),
                                    },
                                )
                            )
                        anchor_current_ref = new_ref
                        anchor_strength = _pen_strength(formed_entry)

                    # strong_pen switch on confirmed pen
                    strength = _pen_strength(pen_payload)
                    if anchor_strength is None or strength > float(anchor_strength or -1.0):
                        new_ref = _pen_ref_from_pen(pen_payload, kind="confirmed")
                        if should_append_switch(old_anchor=anchor_current_ref, new_anchor=new_ref):
                            key_switch = (
                                f"strong_pen:{int(visible_time)}:{new_ref['kind']}:{new_ref['start_time']}:{new_ref['end_time']}:{new_ref['direction']}"
                            )
                            events.append(
                                FactorEventWrite(
                                    series_id=series_id,
                                    factor_name="anchor",
                                    candle_time=int(visible_time),
                                    kind="anchor.switch",
                                    event_key=key_switch,
                                    payload={
                                        "switch_time": int(visible_time),
                                        "reason": "strong_pen",
                                        "old_anchor": dict(anchor_current_ref) if isinstance(anchor_current_ref, dict) else None,
                                        "new_anchor": dict(new_ref),
                                        "visible_time": int(visible_time),
                                    },
                                )
                            )
                        anchor_current_ref = new_ref
                        anchor_strength = float(strength)
            pivot_time_minor = int(visible_time) - int(s.pivot_window_minor) * int(tf_s)
            minor_candidates = _compute_minor_candidates(
                candles=candles,
                time_to_idx=time_to_idx,
                pivot_time=int(pivot_time_minor),
                visible_time=int(visible_time),
                window=int(s.pivot_window_minor),
                segment_start_idx=last_major_idx,
            )
            minor_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))
            for m in minor_candidates:
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
                            "pivot_idx": int(m.pivot_idx) if m.pivot_idx is not None else None,
                        },
                    )
                )

            # strong_pen switch on candidate pen (head)
            last_pen = confirmed_pens[-1] if confirmed_pens else None
            candidate = build_pen_head_candidate(candles=candles, last_confirmed=last_pen, aligned_time=int(visible_time))
            if candidate is not None:
                strength = _pen_strength(candidate)
                if anchor_strength is None or strength > float(anchor_strength or -1.0):
                    new_ref = _pen_ref_from_pen(candidate, kind="candidate")
                    if should_append_switch(old_anchor=anchor_current_ref, new_anchor=new_ref):
                        key_switch = (
                            f"strong_pen:{int(visible_time)}:{new_ref['kind']}:{new_ref['start_time']}:{new_ref['end_time']}:{new_ref['direction']}"
                        )
                        events.append(
                            FactorEventWrite(
                                series_id=series_id,
                                factor_name="anchor",
                                candle_time=int(visible_time),
                                kind="anchor.switch",
                                event_key=key_switch,
                                payload={
                                    "switch_time": int(visible_time),
                                    "reason": "strong_pen",
                                    "old_anchor": dict(anchor_current_ref) if isinstance(anchor_current_ref, dict) else None,
                                    "new_anchor": dict(new_ref),
                                    "visible_time": int(visible_time),
                                },
                            )
                        )
                    anchor_current_ref = new_ref
                    anchor_strength = float(strength)

        # Head snapshots (append-only via seq).
        pen_head: dict[str, Any] = {}
        if confirmed_pens:
            last_pen = confirmed_pens[-1]
            candidate = build_pen_head_candidate(candles=candles, last_confirmed=last_pen, aligned_time=int(up_to))
            if candidate is not None:
                pen_head["candidate"] = candidate

        zhongshu_head: dict[str, Any] = {}
        if confirmed_pens:
            alive = build_alive_zhongshu_from_confirmed_pens(confirmed_pens, up_to_visible_time=int(up_to))
            if alive is not None and int(alive.visible_time) == int(up_to):
                zhongshu_head["alive"] = [
                    {
                        "start_time": int(alive.start_time),
                        "end_time": int(alive.end_time),
                        "zg": float(alive.zg),
                        "zd": float(alive.zd),
                        "formed_time": int(alive.formed_time),
                        "death_time": None,
                        "visible_time": int(alive.visible_time),
                    }
                ]

        anchor_head: dict[str, Any] = {}
        if confirmed_pens or anchor_current_ref is not None:
            current_anchor_ref = anchor_current_ref
            reverse_anchor_ref = None
            if isinstance(pen_head.get("candidate"), dict):
                cand = pen_head.get("candidate") or {}
                reverse_anchor_ref = {
                    "kind": "candidate",
                    "start_time": int(cand.get("start_time") or 0),
                    "end_time": int(cand.get("end_time") or 0),
                    "direction": int(cand.get("direction") or 0),
                }
            anchor_head = {
                "current_anchor_ref": current_anchor_ref,
                "reverse_anchor_ref": reverse_anchor_ref,
            }

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
            if zhongshu_head.get("alive"):
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
