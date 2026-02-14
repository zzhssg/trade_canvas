from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PivotMajorPoint:
    pivot_time: int
    pivot_price: float
    direction: str  # "resistance" | "support"
    visible_time: int
    pivot_idx: int | None = None


@dataclass(frozen=True, slots=True)
class ConfirmedPen:
    start_time: int
    end_time: int
    start_price: float
    end_price: float
    direction: int  # +1 up, -1 down
    visible_time: int
    start_idx: int | None = None
    end_idx: int | None = None


def _is_more_extreme(prev: PivotMajorPoint, cur: PivotMajorPoint) -> bool:
    if cur.direction != prev.direction:
        return False
    if cur.direction == "resistance":
        return float(cur.pivot_price) > float(prev.pivot_price)
    return float(cur.pivot_price) < float(prev.pivot_price)


def build_confirmed_pen(
    *,
    start: PivotMajorPoint,
    end: PivotMajorPoint,
    confirmer: PivotMajorPoint,
) -> ConfirmedPen:
    direction = 1 if float(end.pivot_price) > float(start.pivot_price) else -1
    return ConfirmedPen(
        start_time=int(start.pivot_time),
        end_time=int(end.pivot_time),
        start_price=float(start.pivot_price),
        end_price=float(end.pivot_price),
        direction=int(direction),
        visible_time=int(confirmer.visible_time),
        start_idx=start.pivot_idx,
        end_idx=end.pivot_idx,
    )


def build_confirmed_pens_from_major_pivots(majors: list[PivotMajorPoint]) -> list[ConfirmedPen]:
    """
    Build confirmed pens (append-only semantics) from confirmed major pivots.

    trade_system-aligned minimal semantics:
    - Maintain effective pivots: consecutive same-direction pivots are replaced by the more extreme one.
    - When an opposite-direction pivot is appended, it confirms the previous pen:
        effective[-3] -> effective[-2] becomes confirmed at visible_time = effective[-1].visible_time
      i.e. pen confirmation requires the "next reverse pivot" (3 pivots total).
    """
    if not majors:
        return []

    # Ensure chronological by visible_time then pivot_time.
    pivots = sorted(
        majors,
        key=lambda p: (int(p.visible_time), int(p.pivot_time), str(p.direction), float(p.pivot_price)),
    )

    effective: list[PivotMajorPoint] = []
    out: list[ConfirmedPen] = []

    for p in pivots:
        if not effective:
            effective.append(p)
            continue

        last = effective[-1]
        if p.direction == last.direction:
            if _is_more_extreme(last, p):
                effective[-1] = p
            continue

        effective.append(p)
        if len(effective) < 3:
            continue

        p0 = effective[-3]
        p1 = effective[-2]
        confirmer = effective[-1]
        out.append(build_confirmed_pen(start=p0, end=p1, confirmer=confirmer))

    return out
