from __future__ import annotations

from typing import Any

from .anchor_semantics import build_anchor_history_from_switches
from .factor_store import FactorStore
from .schemas import FactorMetaV1, FactorSliceV1, GetFactorSlicesResponseV1
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .zhongshu import build_alive_zhongshu_from_confirmed_pens


def _is_visible(payload: dict, *, at_time: int) -> bool:
    vt = payload.get("visible_time")
    if vt is None:
        return True
    try:
        return int(vt) <= int(at_time)
    except Exception:
        return True


def _is_more_extreme_pivot(prev: dict, cur: dict) -> bool:
    direction = str(cur.get("direction") or "")
    if direction != str(prev.get("direction") or ""):
        return False
    try:
        cur_price = float(cur.get("pivot_price") or 0.0)
        prev_price = float(prev.get("pivot_price") or 0.0)
    except Exception:
        return False
    if direction == "resistance":
        return cur_price > prev_price
    if direction == "support":
        return cur_price < prev_price
    return False


def _build_effective_major_pivots(*, major_pivots: list[dict], at_time: int) -> list[dict]:
    items: list[dict] = []
    for p in major_pivots:
        direction = str(p.get("direction") or "")
        try:
            pivot_time = int(p.get("pivot_time") or 0)
            pivot_price = float(p.get("pivot_price") or 0.0)
        except Exception:
            continue
        if direction not in {"support", "resistance"}:
            continue
        if pivot_time <= 0 or pivot_time > int(at_time):
            continue
        items.append(
            {
                "pivot_time": int(pivot_time),
                "pivot_price": float(pivot_price),
                "direction": direction,
                "visible_time": int(p.get("visible_time") or 0),
            }
        )
    items.sort(key=lambda d: (int(d.get("visible_time") or 0), int(d.get("pivot_time") or 0)))

    effective: list[dict] = []
    for p in items:
        if not effective:
            effective.append(p)
            continue
        last = effective[-1]
        if str(last.get("direction") or "") == str(p.get("direction") or ""):
            if _is_more_extreme_pivot(last, p):
                effective[-1] = p
            continue
        effective.append(p)
    return effective


def _pick_extreme_after(*, candles: list[Any], start_time: int, pick: str) -> tuple[int, float] | None:
    if pick not in {"high", "low"}:
        return None
    best_time = 0
    best_price = 0.0
    found = False
    for c in candles:
        try:
            t = int(c.candle_time)
        except Exception:
            continue
        if t <= int(start_time):
            continue
        try:
            price = float(c.high) if pick == "high" else float(c.low)
        except Exception:
            continue
        if not found:
            best_time = int(t)
            best_price = float(price)
            found = True
            continue
        if pick == "high":
            if price > best_price or (price == best_price and t < best_time):
                best_time = int(t)
                best_price = float(price)
        else:
            if price < best_price or (price == best_price and t < best_time):
                best_time = int(t)
                best_price = float(price)
    if not found:
        return None
    return (int(best_time), float(best_price))


def build_pen_head_preview(
    *,
    candles: list[Any],
    major_pivots: list[dict],
    aligned_time: int,
) -> dict[str, dict]:
    candles_tail = [c for c in candles if int(c.candle_time) <= int(aligned_time)]
    if not candles_tail:
        return {}
    effective = _build_effective_major_pivots(major_pivots=major_pivots, at_time=int(aligned_time))
    if len(effective) < 2:
        return {}

    start_pivot = effective[-2]
    start_time = int(start_pivot.get("pivot_time") or 0)
    start_price = float(start_pivot.get("pivot_price") or 0.0)
    start_dir = str(start_pivot.get("direction") or "")
    if start_time <= 0 or start_dir not in {"support", "resistance"}:
        return {}

    extending_pick = "high" if start_dir == "support" else "low"
    extending_direction = 1 if extending_pick == "high" else -1
    first = _pick_extreme_after(candles=candles_tail, start_time=int(start_time), pick=extending_pick)
    if first is None:
        return {}
    ext_end_time, ext_end_price = first
    if ext_end_time <= int(start_time) or float(ext_end_price) == float(start_price):
        return {}

    extending = {
        "start_time": int(start_time),
        "end_time": int(ext_end_time),
        "start_price": float(start_price),
        "end_price": float(ext_end_price),
        "direction": int(extending_direction),
    }

    out: dict[str, dict] = {"extending": extending}
    candidate_pick = "low" if extending_direction > 0 else "high"
    candidate_direction = -int(extending_direction)
    second = _pick_extreme_after(candles=candles_tail, start_time=int(ext_end_time), pick=candidate_pick)
    if second is not None:
        cand_end_time, cand_end_price = second
        if cand_end_time > int(ext_end_time) and float(cand_end_price) != float(ext_end_price):
            out["candidate"] = {
                "start_time": int(ext_end_time),
                "end_time": int(cand_end_time),
                "start_price": float(ext_end_price),
                "end_price": float(cand_end_price),
                "direction": int(candidate_direction),
            }
    return out


def build_pen_head_candidate(
    *,
    candles: list[Any],
    last_confirmed: dict | None,
    aligned_time: int,
) -> dict | None:
    if not last_confirmed:
        return None

    try:
        last_end_time = int(last_confirmed.get("end_time") or 0)
        last_end_price = float(last_confirmed.get("end_price") or 0.0)
        last_dir = int(last_confirmed.get("direction") or 0)
    except Exception:
        return None

    if last_end_time <= 0 or last_dir not in (-1, 1):
        return None

    tail = [c for c in candles if int(c.candle_time) > int(last_end_time) and int(c.candle_time) <= int(aligned_time)]
    if not tail:
        return None

    if last_dir == 1:
        best = min(tail, key=lambda c: float(c.low))
        return {
            "start_time": int(last_end_time),
            "end_time": int(best.candle_time),
            "start_price": float(last_end_price),
            "end_price": float(best.low),
            "direction": -1,
        }

    best = max(tail, key=lambda c: float(c.high))
    return {
        "start_time": int(last_end_time),
        "end_time": int(best.candle_time),
        "start_price": float(last_end_price),
        "end_price": float(best.high),
        "direction": 1,
    }


def build_factor_slices(
    *,
    candle_store: CandleStore,
    factor_store: FactorStore,
    series_id: str,
    at_time: int,
    window_candles: int,
) -> GetFactorSlicesResponseV1:
    aligned = candle_store.floor_time(series_id, at_time=int(at_time))
    if aligned is None:
        return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=None)

    tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    start_time = max(0, int(aligned) - int(window_candles) * int(tf_s))

    factor_rows = factor_store.get_events_between_times(
        series_id=series_id,
        factor_name=None,
        start_candle_time=int(start_time),
        end_candle_time=int(aligned),
    )

    piv_major: list[dict] = []
    piv_minor: list[dict] = []
    pen_confirmed: list[dict] = []
    zhongshu_dead: list[dict] = []
    anchor_switches: list[dict] = []

    for r in factor_rows:
        if r.factor_name == "pivot" and r.kind == "pivot.major":
            payload = dict(r.payload or {})
            if _is_visible(payload, at_time=int(aligned)):
                piv_major.append(payload)
        elif r.factor_name == "pivot" and r.kind == "pivot.minor":
            payload = dict(r.payload or {})
            if _is_visible(payload, at_time=int(aligned)):
                piv_minor.append(payload)
        elif r.factor_name == "pen" and r.kind == "pen.confirmed":
            payload = dict(r.payload or {})
            if _is_visible(payload, at_time=int(aligned)):
                pen_confirmed.append(payload)
        elif r.factor_name == "zhongshu" and r.kind == "zhongshu.dead":
            payload = dict(r.payload or {})
            if _is_visible(payload, at_time=int(aligned)):
                zhongshu_dead.append(payload)
        elif r.factor_name == "anchor" and r.kind == "anchor.switch":
            payload = dict(r.payload or {})
            if _is_visible(payload, at_time=int(aligned)):
                anchor_switches.append(payload)

    piv_major.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("pivot_time", 0))))
    pen_confirmed.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("start_time", 0))))
    anchor_switches.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("switch_time", 0))))

    snapshots: dict[str, FactorSliceV1] = {}
    factors: list[str] = []
    candle_id = f"{series_id}:{int(aligned)}"

    if piv_major:
        factors.append("pivot")
        snapshots["pivot"] = FactorSliceV1(
            history={"major": piv_major, "minor": piv_minor},
            head={},
            meta=FactorMetaV1(
                series_id=series_id,
                at_time=int(aligned),
                candle_id=candle_id,
                factor_name="pivot",
            ),
        )

    pen_head: dict[str, Any] = {}
    if pen_confirmed:
        try:
            candles = candle_store.get_closed(series_id, since=int(start_time), limit=int(window_candles) + 5)
            candles = [c for c in candles if int(c.candle_time) <= int(aligned)]
        except Exception:
            candles = []

        preview = build_pen_head_preview(candles=candles, major_pivots=piv_major, aligned_time=int(aligned))
        for key in ("extending", "candidate"):
            v = preview.get(key)
            if isinstance(v, dict):
                pen_head[key] = v

        factors.append("pen")
        snapshots["pen"] = FactorSliceV1(
            history={"confirmed": pen_confirmed},
            head=pen_head,
            meta=FactorMetaV1(
                series_id=series_id,
                at_time=int(aligned),
                candle_id=candle_id,
                factor_name="pen",
            ),
        )

    # Zhongshu head.alive is derived from confirmed pens at t (head-only); dead is append-only history slice.
    zhongshu_head: dict[str, Any] = {}
    if pen_confirmed:
        try:
            alive = build_alive_zhongshu_from_confirmed_pens(pen_confirmed, up_to_visible_time=int(aligned))
        except Exception:
            alive = None
        if alive is not None and int(alive.visible_time) == int(aligned):
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

    if zhongshu_dead or zhongshu_head.get("alive"):
        factors.append("zhongshu")
        snapshots["zhongshu"] = FactorSliceV1(
            history={"dead": zhongshu_dead},
            head=zhongshu_head,
            meta=FactorMetaV1(
                series_id=series_id,
                at_time=int(aligned),
                candle_id=candle_id,
                factor_name="zhongshu",
            ),
        )

    # Anchor snapshot:
    # - history.switches: append-only stable switches from FactorStore
    # - head.current_anchor_ref: the latest switch new_anchor (if available)
    # - head.reverse_anchor_ref: optional (candidate pen derived from pen head)
    if pen_confirmed or anchor_switches:
        history_anchors, history_switches = build_anchor_history_from_switches(anchor_switches)
        current_anchor_ref = None
        if history_switches:
            cur = history_switches[-1].get("new_anchor")
            if isinstance(cur, dict):
                current_anchor_ref = cur
        elif pen_confirmed:
            last = pen_confirmed[-1]
            current_anchor_ref = {
                "kind": "confirmed",
                "start_time": int(last.get("start_time") or 0),
                "end_time": int(last.get("end_time") or 0),
                "direction": int(last.get("direction") or 0),
            }

        reverse_anchor_ref = None
        pen_head_candidate = pen_head.get("candidate") if pen_head else None
        if isinstance(pen_head_candidate, dict):
            try:
                reverse_anchor_ref = {
                    "kind": "candidate",
                    "start_time": int(pen_head_candidate.get("start_time") or 0),
                    "end_time": int(pen_head_candidate.get("end_time") or 0),
                    "direction": int(pen_head_candidate.get("direction") or 0),
                }
            except Exception:
                reverse_anchor_ref = None

        factors.append("anchor")
        snapshots["anchor"] = FactorSliceV1(
            history={"anchors": history_anchors, "switches": history_switches},
            head={"current_anchor_ref": current_anchor_ref, "reverse_anchor_ref": reverse_anchor_ref},
            meta=FactorMetaV1(
                series_id=series_id,
                at_time=int(aligned),
                candle_id=candle_id,
                factor_name="anchor",
            ),
        )

    return GetFactorSlicesResponseV1(
        series_id=series_id,
        at_time=int(aligned),
        candle_id=candle_id,
        factors=factors,
        snapshots=snapshots,
    )
