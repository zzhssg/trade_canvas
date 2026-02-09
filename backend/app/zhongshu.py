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


@dataclass(frozen=True)
class ZhongshuAlive:
    start_time: int
    end_time: int
    zg: float  # upper bound
    zd: float  # lower bound
    entry_direction: int  # entry pen direction: 1=up, -1=down
    formed_time: int
    visible_time: int


def _as_range(pen: dict) -> tuple[float, float] | None:
    sp = pen.get("start_price")
    ep = pen.get("end_price")
    try:
        a = float(sp)
        b = float(ep)
    except Exception:
        return None
    lo = a if a <= b else b
    hi = b if a <= b else a
    return (lo, hi)


def _entry_direction(pen: dict) -> int:
    try:
        direction = int(pen.get("direction") or 0)
    except Exception:
        direction = 0
    if direction in {-1, 1}:
        return int(direction)

    r = _as_range(pen)
    if r is None:
        return 1
    try:
        sp = float(pen.get("start_price"))
        ep = float(pen.get("end_price"))
    except Exception:
        return 1
    return 1 if ep >= sp else -1


def _try_form_from_tail(window: list[dict]) -> tuple[dict | None, dict | None]:
    # Formation rule: entry pen + next 3 pens.
    if len(window) < 4:
        return None, None

    entry_pen = window[-4]
    trio = window[-3:]
    ranges = [_as_range(p) for p in trio]
    if any(r is None for r in ranges):
        return None, None

    lo = max(r[0] for r in ranges if r is not None)
    hi = min(r[1] for r in ranges if r is not None)
    if lo > hi:
        return None, None

    formed_pen = trio[-1]
    formed_time = int(formed_pen.get("visible_time") or 0)
    if formed_time <= 0:
        return None, None

    start_time = int(entry_pen.get("start_time") or 0)
    end_time = int(formed_pen.get("end_time") or 0)
    if start_time <= 0 or end_time <= 0:
        return None, None

    return (
        {
            "start_time": start_time,
            "end_time": end_time,
            "zg": float(hi),
            "zd": float(lo),
            "entry_direction": int(_entry_direction(entry_pen)),
            "formed_time": formed_time,
            "last_seen_visible_time": formed_time,
        },
        entry_pen,
    )


def _is_same_side_outside(alive: dict, pen: dict) -> bool:
    r = _as_range(pen)
    if r is None:
        return False
    zd = float(alive.get("zd") or 0.0)
    zg = float(alive.get("zg") or 0.0)
    pen_lo, pen_hi = float(r[0]), float(r[1])
    return pen_hi < zd or pen_lo > zg


def init_zhongshu_state() -> dict[str, Any]:
    return {"alive": None, "tail": []}


def update_zhongshu_state(state: dict[str, Any], pen: dict) -> tuple[ZhongshuDead | None, dict | None]:
    tail: list[dict] = list(state.get("tail") or [])
    tail.append(pen)
    if len(tail) > 4:
        tail = tail[-4:]

    alive = state.get("alive")
    formed_entry_pen: dict | None = None
    dead_event: ZhongshuDead | None = None

    if _as_range(pen) is None:
        state["tail"] = tail
        return None, None

    if alive is None:
        alive, formed_entry_pen = _try_form_from_tail(tail)
    else:
        # Keep zg/zd fixed after formation; only end_time advances.
        if _is_same_side_outside(alive, pen):
            visible_time = int(pen.get("visible_time") or 0)
            dead_event = ZhongshuDead(
                start_time=int(alive["start_time"]),
                end_time=int(alive.get("end_time") or 0),
                zg=float(alive["zg"]),
                zd=float(alive["zd"]),
                entry_direction=int(alive.get("entry_direction") or 1),
                formed_time=int(alive["formed_time"]),
                death_time=int(visible_time),
                visible_time=int(visible_time),
            )
            alive, formed_entry_pen = _try_form_from_tail(tail)
        else:
            try:
                alive["end_time"] = max(int(alive.get("end_time") or 0), int(pen.get("end_time") or 0))
            except Exception:
                pass
            alive["last_seen_visible_time"] = int(pen.get("visible_time") or 0)

    state["alive"] = alive
    state["tail"] = tail
    return dead_event, formed_entry_pen


def replay_zhongshu_state(pens: list[dict]) -> dict[str, Any]:
    items: list[tuple[int, dict]] = []
    for p in pens:
        try:
            vt = int(p.get("visible_time") or 0)
        except Exception:
            vt = 0
        if vt <= 0:
            continue
        items.append((vt, p))
    items.sort(key=lambda x: x[0])

    state = init_zhongshu_state()
    for _, p in items:
        update_zhongshu_state(state, p)
    return state


def build_alive_zhongshu_from_confirmed_pens(
    pens: list[dict],
    *,
    up_to_visible_time: int,
) -> ZhongshuAlive | None:
    """
    Compute the t-time alive zhongshu snapshot (head-only):
    - Uses only confirmed pens with visible_time<=t (no future function).
    - Replays the same semantics as build_dead_zhongshus_from_confirmed_pens.
    - Returns the last alive zhongshu at t (0/1).
    """
    t = int(up_to_visible_time or 0)
    if t <= 0:
        return None

    items: list[tuple[int, dict]] = []
    for p in pens:
        try:
            vt = int(p.get("visible_time") or 0)
        except Exception:
            vt = 0
        if vt <= 0 or vt > t:
            continue
        items.append((vt, p))
    items.sort(key=lambda x: x[0])
    if not items:
        return None

    state = init_zhongshu_state()
    for _, pen in items:
        update_zhongshu_state(state, pen)

    alive = state.get("alive")
    if alive is None:
        return None

    try:
        start_time = int(alive.get("start_time") or 0)
        end_time = int(alive.get("end_time") or 0)
        zg = float(alive.get("zg") or 0.0)
        zd = float(alive.get("zd") or 0.0)
        entry_direction = int(alive.get("entry_direction") or 1)
        formed_time = int(alive.get("formed_time") or 0)
    except Exception:
        return None
    if start_time <= 0 or end_time <= 0 or formed_time <= 0:
        return None
    if zd > zg:
        return None

    return ZhongshuAlive(
        start_time=start_time,
        end_time=end_time,
        zg=zg,
        zd=zd,
        entry_direction=entry_direction if entry_direction in {-1, 1} else 1,
        formed_time=formed_time,
        visible_time=int(t),
    )


def build_dead_zhongshus_from_confirmed_pens(pens: list[dict]) -> list[ZhongshuDead]:
    """
    Forward-growing Zhongshu semantics (append-only dead events):
    - Consumes confirmed pens only.
    - Forms with entry pen + next 3 pens (range from the latter 3).
    - Keeps zg/zd fixed after formation.
    - Dies when a new pen is fully above or fully below the zhongshu zone.
    """
    items = []
    for p in pens:
        try:
            vt = int(p.get("visible_time") or 0)
        except Exception:
            vt = 0
        if vt <= 0:
            continue
        items.append((vt, p))
    items.sort(key=lambda x: x[0])

    state = init_zhongshu_state()
    out: list[ZhongshuDead] = []
    for _, pen in items:
        dead_event, _ = update_zhongshu_state(state, pen)
        if dead_event is not None:
            out.append(dead_event)

    return out
