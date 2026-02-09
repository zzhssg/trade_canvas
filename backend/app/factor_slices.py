from __future__ import annotations

from typing import Any


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
