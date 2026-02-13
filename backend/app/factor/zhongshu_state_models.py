from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ZhongshuDead:
    start_time: int
    end_time: int
    zg: float  # upper bound
    zd: float  # lower bound
    entry_direction: int  # entry pen direction: 1=up, -1=down
    formed_time: int
    death_time: int
    visible_time: int
    formed_reason: str = "pen_confirmed"


@dataclass(frozen=True)
class ZhongshuAlive:
    start_time: int
    end_time: int
    zg: float  # upper bound
    zd: float  # lower bound
    entry_direction: int  # entry pen direction: 1=up, -1=down
    formed_time: int
    visible_time: int
    formed_reason: str = "pen_confirmed"


@dataclass
class _PendingZhongshu:
    entry_pen: dict
    p1_pen: dict
    p2_pen: dict
    entry_range: tuple[float, float]
    p1_range: tuple[float, float]
    p2_range: tuple[float, float]
    p3_direction: int
    p3_start_time: int
    p3_start_price: float
    p3_extreme_price: float
    p3_extreme_time: int
    trigger_price: float
    cross_time: int | None


@dataclass
class _AliveZhongshu:
    start_time: int
    end_time: int
    zg: float
    zd: float
    entry_direction: int
    formed_time: int
    formed_reason: str
    last_seen_visible_time: int
    awaiting_p3_confirm: bool
    p3_start_time: int


def _coerce_range(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lo = float(value[0])
        hi = float(value[1])
    except (ValueError, TypeError):
        return None
    return (float(lo), float(hi))


def _pending_from_dict(raw: Any) -> _PendingZhongshu | None:
    if not isinstance(raw, dict):
        return None
    entry_pen = dict(raw.get("entry_pen") or {})
    p1_pen = dict(raw.get("p1_pen") or {})
    p2_pen = dict(raw.get("p2_pen") or {})
    entry_range = _coerce_range(raw.get("entry_range"))
    p1_range = _coerce_range(raw.get("p1_range"))
    p2_range = _coerce_range(raw.get("p2_range"))
    if entry_range is None or p1_range is None or p2_range is None:
        return None
    try:
        p3_direction = int(raw.get("p3_direction") or 0)
        p3_start_time = int(raw.get("p3_start_time") or 0)
        p3_start_price = float(raw.get("p3_start_price") or 0.0)
        p3_extreme_price = float(raw.get("p3_extreme_price") or p3_start_price)
        p3_extreme_time = int(raw.get("p3_extreme_time") or p3_start_time)
        trigger_price = float(raw.get("trigger_price") or 0.0)
    except (ValueError, TypeError):
        return None
    cross_time_raw = raw.get("cross_time")
    try:
        cross_time = int(cross_time_raw) if cross_time_raw is not None else None
    except (ValueError, TypeError):
        cross_time = None
    if p3_direction not in {-1, 1} or p3_start_time <= 0:
        return None
    return _PendingZhongshu(
        entry_pen=entry_pen,
        p1_pen=p1_pen,
        p2_pen=p2_pen,
        entry_range=entry_range,
        p1_range=p1_range,
        p2_range=p2_range,
        p3_direction=int(p3_direction),
        p3_start_time=int(p3_start_time),
        p3_start_price=float(p3_start_price),
        p3_extreme_price=float(p3_extreme_price),
        p3_extreme_time=int(p3_extreme_time),
        trigger_price=float(trigger_price),
        cross_time=cross_time,
    )


def _pending_to_dict(pending: _PendingZhongshu | None) -> dict | None:
    if pending is None:
        return None
    return {
        "entry_pen": dict(pending.entry_pen),
        "p1_pen": dict(pending.p1_pen),
        "p2_pen": dict(pending.p2_pen),
        "entry_range": tuple(pending.entry_range),
        "p1_range": tuple(pending.p1_range),
        "p2_range": tuple(pending.p2_range),
        "p3_direction": int(pending.p3_direction),
        "p3_start_time": int(pending.p3_start_time),
        "p3_start_price": float(pending.p3_start_price),
        "p3_extreme_price": float(pending.p3_extreme_price),
        "p3_extreme_time": int(pending.p3_extreme_time),
        "trigger_price": float(pending.trigger_price),
        "cross_time": None if pending.cross_time is None else int(pending.cross_time),
    }


def _alive_from_dict(raw: Any) -> _AliveZhongshu | None:
    if not isinstance(raw, dict):
        return None
    try:
        start_time = int(raw.get("start_time") or 0)
        end_time = int(raw.get("end_time") or 0)
        zg = float(raw.get("zg") or 0.0)
        zd = float(raw.get("zd") or 0.0)
        entry_direction = int(raw.get("entry_direction") or 1)
        formed_time = int(raw.get("formed_time") or 0)
        formed_reason = str(raw.get("formed_reason") or "pen_confirmed")
        last_seen_visible_time = int(raw.get("last_seen_visible_time") or 0)
        awaiting_p3_confirm = bool(raw.get("awaiting_p3_confirm"))
        p3_start_time = int(raw.get("p3_start_time") or 0)
    except (ValueError, TypeError):
        return None
    if start_time <= 0 or end_time <= 0 or formed_time <= 0:
        return None
    if zd > zg:
        return None
    if entry_direction not in {-1, 1}:
        entry_direction = 1
    return _AliveZhongshu(
        start_time=int(start_time),
        end_time=int(end_time),
        zg=float(zg),
        zd=float(zd),
        entry_direction=int(entry_direction),
        formed_time=int(formed_time),
        formed_reason=str(formed_reason),
        last_seen_visible_time=int(last_seen_visible_time),
        awaiting_p3_confirm=bool(awaiting_p3_confirm),
        p3_start_time=int(p3_start_time),
    )


def _alive_to_dict(alive: _AliveZhongshu | None) -> dict | None:
    if alive is None:
        return None
    return {
        "start_time": int(alive.start_time),
        "end_time": int(alive.end_time),
        "zg": float(alive.zg),
        "zd": float(alive.zd),
        "entry_direction": int(alive.entry_direction),
        "formed_time": int(alive.formed_time),
        "formed_reason": str(alive.formed_reason),
        "last_seen_visible_time": int(alive.last_seen_visible_time),
        "awaiting_p3_confirm": bool(alive.awaiting_p3_confirm),
        "p3_start_time": int(alive.p3_start_time),
    }


def _as_range(pen: dict) -> tuple[float, float] | None:
    sp = pen.get("start_price")
    ep = pen.get("end_price")
    if sp is None or ep is None:
        return None
    try:
        a = float(sp)
        b = float(ep)
    except (ValueError, TypeError):
        return None
    lo = a if a <= b else b
    hi = b if a <= b else a
    return (lo, hi)


def _intersects_non_empty(ranges: list[tuple[float, float]]) -> bool:
    if not ranges:
        return False
    lo = max(r[0] for r in ranges)
    hi = min(r[1] for r in ranges)
    return lo <= hi


def _build_zone_from_trio(r1: tuple[float, float], r2: tuple[float, float], r3: tuple[float, float]) -> tuple[float, float] | None:
    lo = max(r1[0], r2[0], r3[0])  # zd
    hi = min(r1[1], r2[1], r3[1])  # zg
    if lo > hi:
        return None
    return (float(lo), float(hi))


def _entry_direction(pen: dict) -> int:
    try:
        direction = int(pen.get("direction") or 0)
    except (ValueError, TypeError):
        direction = 0
    if direction in {-1, 1}:
        return int(direction)

    r = _as_range(pen)
    if r is None:
        return 1
    sp_raw = pen.get("start_price")
    ep_raw = pen.get("end_price")
    if sp_raw is None or ep_raw is None:
        return 1
    try:
        sp = float(sp_raw)
        ep = float(ep_raw)
    except (ValueError, TypeError):
        return 1
    return 1 if ep >= sp else -1
