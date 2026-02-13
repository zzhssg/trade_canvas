from __future__ import annotations

from dataclasses import dataclass

from .zhongshu_state_models import (
    _AliveZhongshu,
    _PendingZhongshu,
    _as_range,
    _build_zone_from_trio,
    _entry_direction,
    _intersects_non_empty,
)


@dataclass(frozen=True)
class _AliveBuildInput:
    entry_pen: dict
    p1_range: tuple[float, float]
    p2_range: tuple[float, float]
    p3_range: tuple[float, float]
    formed_time: int
    visible_time: int
    end_time: int
    formed_reason: str
    awaiting_p3_confirm: bool
    p3_start_time: int


def _build_pending_from_tail(
    tail: list[dict],
    *,
    min_entry_start_time: int | None = None,
) -> _PendingZhongshu | None:
    if len(tail) < 3:
        return None
    entry_pen = tail[-3]
    p1_pen = tail[-2]
    p2_pen = tail[-1]
    if min_entry_start_time is not None:
        try:
            entry_start_time = int(entry_pen.get("start_time") or 0)
        except (ValueError, TypeError):
            entry_start_time = 0
        if entry_start_time <= 0 or entry_start_time < int(min_entry_start_time):
            return None
    entry_range = _as_range(entry_pen)
    p1_range = _as_range(p1_pen)
    p2_range = _as_range(p2_pen)
    if entry_range is None or p1_range is None or p2_range is None:
        return None

    try:
        p2_direction = int(p2_pen.get("direction") or 0)
    except (ValueError, TypeError):
        p2_direction = 0
    if p2_direction not in {-1, 1}:
        p2_direction = _entry_direction(p2_pen)
    p3_direction = -int(p2_direction)

    p3_start_time = int(p2_pen.get("end_time") or 0)
    p3_start_price = float(p2_pen.get("end_price") or 0.0)
    if p3_start_time <= 0:
        return None

    trigger_price = float(p1_pen.get("end_price") or 0.0)
    return _PendingZhongshu(
        entry_pen=dict(entry_pen),
        p1_pen=dict(p1_pen),
        p2_pen=dict(p2_pen),
        entry_range=entry_range,
        p1_range=p1_range,
        p2_range=p2_range,
        p3_direction=int(p3_direction),
        p3_start_time=int(p3_start_time),
        p3_start_price=float(p3_start_price),
        p3_extreme_price=float(p3_start_price),
        p3_extreme_time=int(p3_start_time),
        trigger_price=float(trigger_price),
        cross_time=None,
    )


def _pending_candidate_range(pending: _PendingZhongshu) -> tuple[float, float]:
    sp = float(pending.p3_start_price)
    ep = float(pending.p3_extreme_price)
    lo = sp if sp <= ep else ep
    hi = ep if sp <= ep else sp
    return (float(lo), float(hi))


def _build_alive_from_parts(
    *,
    request: _AliveBuildInput,
) -> _AliveZhongshu | None:
    entry_range = _as_range(request.entry_pen)
    if entry_range is None:
        return None
    if not _intersects_non_empty([entry_range, request.p1_range, request.p2_range, request.p3_range]):
        return None
    zone = _build_zone_from_trio(request.p1_range, request.p2_range, request.p3_range)
    if zone is None:
        return None
    zd, zg = zone
    start_time = int(request.entry_pen.get("start_time") or 0)
    if start_time <= 0 or int(request.end_time) <= 0:
        return None
    if int(request.formed_time) <= 0 or int(request.visible_time) <= 0:
        return None
    if int(request.formed_time) > int(request.visible_time):
        return None
    return _AliveZhongshu(
        start_time=int(start_time),
        end_time=int(request.end_time),
        zg=float(zg),
        zd=float(zd),
        entry_direction=int(_entry_direction(request.entry_pen)),
        formed_time=int(request.formed_time),
        formed_reason=str(request.formed_reason),
        last_seen_visible_time=int(request.visible_time),
        awaiting_p3_confirm=bool(request.awaiting_p3_confirm),
        p3_start_time=int(request.p3_start_time),
    )


def _try_form_from_pending_with_confirmed(
    pending: _PendingZhongshu | None, pen: dict
) -> tuple[_AliveZhongshu | None, dict | None]:
    if pending is None:
        return None, None
    try:
        pen_start = int(pen.get("start_time") or 0)
    except (ValueError, TypeError):
        pen_start = 0
    if pen_start <= 0 or pen_start != int(pending.p3_start_time):
        return None, None

    p3_range = _as_range(pen)
    if p3_range is None:
        return None, None
    formed_time = int(pen.get("visible_time") or 0)
    visible_time = int(pen.get("visible_time") or 0)
    end_time = int(pen.get("end_time") or 0)
    if formed_time <= 0 or visible_time <= 0:
        return None, None

    alive = _build_alive_from_parts(
        request=_AliveBuildInput(
            entry_pen=dict(pending.entry_pen),
            p1_range=pending.p1_range,
            p2_range=pending.p2_range,
            p3_range=p3_range,
            formed_time=int(formed_time),
            visible_time=int(visible_time),
            end_time=int(end_time),
            formed_reason="pen_confirmed",
            awaiting_p3_confirm=False,
            p3_start_time=int(pending.p3_start_time),
        ),
    )
    if alive is None:
        return None, None
    return alive, dict(pending.entry_pen)


def _try_form_from_pending_with_cross(
    pending: _PendingZhongshu | None, *, visible_time: int
) -> tuple[_AliveZhongshu | None, dict | None]:
    if pending is None:
        return None, None
    cross_time = int(pending.cross_time or 0)
    if cross_time <= 0 or visible_time <= 0:
        return None, None
    p3_range = _pending_candidate_range(pending)
    end_time = int(visible_time)
    alive = _build_alive_from_parts(
        request=_AliveBuildInput(
            entry_pen=dict(pending.entry_pen),
            p1_range=pending.p1_range,
            p2_range=pending.p2_range,
            p3_range=p3_range,
            formed_time=int(cross_time),
            visible_time=int(visible_time),
            end_time=int(end_time),
            formed_reason="price_cross",
            awaiting_p3_confirm=True,
            p3_start_time=int(pending.p3_start_time),
        ),
    )
    if alive is None:
        return None, None
    return alive, dict(pending.entry_pen)


def _is_same_side_outside(alive: _AliveZhongshu, pen: dict) -> bool:
    r = _as_range(pen)
    if r is None:
        return False
    zd = float(alive.zd)
    zg = float(alive.zg)
    pen_lo, pen_hi = float(r[0]), float(r[1])
    return pen_hi < zd or pen_lo > zg
