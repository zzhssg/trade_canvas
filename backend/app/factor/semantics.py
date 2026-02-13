from __future__ import annotations

from .pen import PivotMajorPoint


def is_more_extreme_direction(*, direction: str, prev_price: float, cur_price: float) -> bool:
    if direction == "resistance":
        return float(cur_price) > float(prev_price)
    if direction == "support":
        return float(cur_price) < float(prev_price)
    return False


def is_more_extreme_pivot(prev: PivotMajorPoint, cur: PivotMajorPoint) -> bool:
    if cur.direction != prev.direction:
        return False
    return is_more_extreme_direction(
        direction=str(cur.direction),
        prev_price=float(prev.pivot_price),
        cur_price=float(cur.pivot_price),
    )


def is_more_extreme_pivot_dict(prev: dict, cur: dict) -> bool:
    direction = str(cur.get("direction") or "")
    if direction != str(prev.get("direction") or ""):
        return False
    try:
        prev_price = float(prev.get("pivot_price") or 0.0)
        cur_price = float(cur.get("pivot_price") or 0.0)
    except Exception:
        return False
    return is_more_extreme_direction(
        direction=direction,
        prev_price=prev_price,
        cur_price=cur_price,
    )
