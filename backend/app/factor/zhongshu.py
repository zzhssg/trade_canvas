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
    entry_pen: dict,
    p1_range: tuple[float, float],
    p2_range: tuple[float, float],
    p3_range: tuple[float, float],
    formed_time: int,
    visible_time: int,
    end_time: int,
    formed_reason: str,
    awaiting_p3_confirm: bool,
    p3_start_time: int,
) -> _AliveZhongshu | None:
    entry_range = _as_range(entry_pen)
    if entry_range is None:
        return None
    if not _intersects_non_empty([entry_range, p1_range, p2_range, p3_range]):
        return None
    zone = _build_zone_from_trio(p1_range, p2_range, p3_range)
    if zone is None:
        return None
    zd, zg = zone
    start_time = int(entry_pen.get("start_time") or 0)
    if start_time <= 0 or end_time <= 0:
        return None
    if formed_time <= 0 or visible_time <= 0 or formed_time > visible_time:
        return None
    return _AliveZhongshu(
        start_time=int(start_time),
        end_time=int(end_time),
        zg=float(zg),
        zd=float(zd),
        entry_direction=int(_entry_direction(entry_pen)),
        formed_time=int(formed_time),
        formed_reason=str(formed_reason),
        last_seen_visible_time=int(visible_time),
        awaiting_p3_confirm=bool(awaiting_p3_confirm),
        p3_start_time=int(p3_start_time),
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


def init_zhongshu_state() -> dict[str, Any]:
    return {"alive": None, "tail": [], "pending": None, "reseed_floor_start_time": 0}


def update_zhongshu_state(state: dict[str, Any], pen: dict) -> tuple[ZhongshuDead | None, dict | None]:
    tail: list[dict] = list(state.get("tail") or [])
    tail.append(pen)
    if len(tail) > 4:
        tail = tail[-4:]

    alive = _alive_from_dict(state.get("alive"))
    pending = _pending_from_dict(state.get("pending"))
    try:
        reseed_floor_start_time = int(state.get("reseed_floor_start_time") or 0)
    except (ValueError, TypeError):
        reseed_floor_start_time = 0
    formed_entry_pen: dict | None = None
    dead_event: ZhongshuDead | None = None

    if _as_range(pen) is None:
        state["tail"] = tail
        state["pending"] = _pending_to_dict(pending)
        state["alive"] = _alive_to_dict(alive)
        state["reseed_floor_start_time"] = int(reseed_floor_start_time)
        return None, None

    if alive is None:
        consumed_pending = False
        if pending is not None:
            try:
                consumed_pending = int(pen.get("start_time") or 0) == int(pending.p3_start_time)
            except (ValueError, TypeError):
                consumed_pending = False
            alive, formed_entry_pen = _try_form_from_pending_with_confirmed(pending, pen)
            if alive is not None:
                pending = None
            elif consumed_pending:
                pending = None
        if alive is None and pending is None:
            pending = _build_pending_from_tail(
                tail,
                min_entry_start_time=int(reseed_floor_start_time) if reseed_floor_start_time > 0 else None,
            )
    else:
        waiting_p3_confirm = bool(alive.awaiting_p3_confirm)
        p3_start_time = int(alive.p3_start_time)
        pen_start_time = int(pen.get("start_time") or 0)
        if waiting_p3_confirm and p3_start_time > 0 and pen_start_time == p3_start_time:
            alive.awaiting_p3_confirm = False
            try:
                alive.end_time = max(int(alive.end_time), int(pen.get("end_time") or 0))
            except (ValueError, TypeError):
                pass
            alive.last_seen_visible_time = int(pen.get("visible_time") or alive.last_seen_visible_time or 0)
            state["alive"] = _alive_to_dict(alive)
            state["tail"] = tail
            state["pending"] = _pending_to_dict(pending)
            return None, None
        # Keep zg/zd fixed after formation; only end_time advances.
        if _is_same_side_outside(alive, pen):
            visible_time = int(pen.get("visible_time") or 0)
            dead_event = ZhongshuDead(
                start_time=int(alive.start_time),
                end_time=int(alive.end_time),
                zg=float(alive.zg),
                zd=float(alive.zd),
                entry_direction=int(alive.entry_direction),
                formed_time=int(alive.formed_time),
                death_time=int(visible_time),
                visible_time=int(visible_time),
                formed_reason=str(alive.formed_reason or "pen_confirmed"),
            )
            if len(tail) >= 2:
                try:
                    reseed_floor_start_time = int(tail[-2].get("start_time") or 0)
                except (ValueError, TypeError):
                    reseed_floor_start_time = 0
            else:
                try:
                    reseed_floor_start_time = int(pen.get("start_time") or 0)
                except (ValueError, TypeError):
                    reseed_floor_start_time = 0
            alive = None
            pending = None
            pending = _build_pending_from_tail(
                tail,
                min_entry_start_time=int(reseed_floor_start_time) if reseed_floor_start_time > 0 else None,
            )
        else:
            try:
                alive.end_time = max(int(alive.end_time), int(pen.get("end_time") or 0))
            except (ValueError, TypeError):
                pass
            alive.last_seen_visible_time = int(pen.get("visible_time") or 0)

    state["pending"] = _pending_to_dict(pending)
    state["alive"] = _alive_to_dict(alive)
    state["tail"] = tail
    state["reseed_floor_start_time"] = int(reseed_floor_start_time)
    return dead_event, formed_entry_pen


def update_zhongshu_state_on_closed_candle(state: dict[str, Any], candle: dict) -> dict | None:
    """
    Apply a closed-candle tick to zhongshu state.

    Formation fast-path:
    - When there is a pending structure (entry + P1 + P2), track P3 as extending candidate.
    - First closed candle where high/low crosses P1.end_price confirms zhongshu early,
      with formed_time fixed at that first cross candle.
    """
    try:
        candle_time = int(candle.get("candle_time") or 0)
        high = float(candle.get("high") or 0.0)
        low = float(candle.get("low") or 0.0)
    except (ValueError, TypeError):
        return None
    if candle_time <= 0:
        return None

    alive = _alive_from_dict(state.get("alive"))
    if alive is not None:
        alive.end_time = max(int(alive.end_time), int(candle_time))
        alive.last_seen_visible_time = int(candle_time)
        state["alive"] = _alive_to_dict(alive)
        return None

    pending = _pending_from_dict(state.get("pending"))
    if pending is None:
        return None
    p3_start_time = int(pending.p3_start_time)
    if candle_time <= p3_start_time:
        return None

    p3_direction = int(pending.p3_direction)
    trigger = float(pending.trigger_price)

    if p3_direction < 0:
        cur_extreme = float(pending.p3_extreme_price)
        if low < cur_extreme:
            pending.p3_extreme_price = float(low)
            pending.p3_extreme_time = int(candle_time)
        crossed = low <= trigger
    else:
        cur_extreme = float(pending.p3_extreme_price)
        if high > cur_extreme:
            pending.p3_extreme_price = float(high)
            pending.p3_extreme_time = int(candle_time)
        crossed = high >= trigger

    if crossed and int(pending.cross_time or 0) <= 0:
        pending.cross_time = int(candle_time)

    formed_entry_pen: dict | None = None
    alive_new, formed_entry_pen = _try_form_from_pending_with_cross(pending, visible_time=int(candle_time))
    if alive_new is not None:
        state["alive"] = _alive_to_dict(alive_new)
        state["pending"] = None
        return formed_entry_pen

    state["pending"] = _pending_to_dict(pending)
    return None


def _collect_pen_items(
    *,
    pens: list[dict],
    up_to_visible_time: int | None = None,
) -> list[tuple[int, dict]]:
    t_limit = int(up_to_visible_time or 0)
    items: list[tuple[int, dict]] = []
    for p in pens:
        try:
            vt = int(p.get("visible_time") or 0)
        except (ValueError, TypeError):
            vt = 0
        if vt <= 0:
            continue
        if t_limit > 0 and vt > t_limit:
            continue
        items.append((int(vt), p))
    items.sort(key=lambda x: x[0])
    return items


def _collect_candle_items(
    *,
    candles: list[Any] | None,
    up_to_visible_time: int | None = None,
) -> list[tuple[int, dict]]:
    if candles is None:
        return []
    t_limit = int(up_to_visible_time or 0)
    items: list[tuple[int, dict]] = []
    for c in candles:
        try:
            ct = int(getattr(c, "candle_time"))
            hi = float(getattr(c, "high"))
            lo = float(getattr(c, "low"))
        except (ValueError, TypeError):
            continue
        if ct <= 0:
            continue
        if t_limit > 0 and ct > t_limit:
            continue
        items.append((int(ct), {"candle_time": int(ct), "high": float(hi), "low": float(lo)}))
    items.sort(key=lambda x: x[0])
    return items


def replay_zhongshu_state(pens: list[dict]) -> dict[str, Any]:
    items = _collect_pen_items(pens=pens, up_to_visible_time=None)

    state = init_zhongshu_state()
    for _, p in items:
        update_zhongshu_state(state, p)
    return state


def replay_zhongshu_state_with_closed_candles(
    *,
    pens: list[dict],
    candles: list[Any],
    up_to_visible_time: int,
) -> dict[str, Any]:
    t = int(up_to_visible_time or 0)
    if t <= 0:
        return init_zhongshu_state()

    pen_items = _collect_pen_items(pens=pens, up_to_visible_time=int(t))
    candle_items = _collect_candle_items(candles=candles, up_to_visible_time=int(t))

    state = init_zhongshu_state()
    pi = 0
    plen = len(pen_items)
    for candle_time, candle_payload in candle_items:
        while pi < plen and int(pen_items[pi][0]) <= int(candle_time):
            _, pen = pen_items[pi]
            update_zhongshu_state(state, pen)
            pi += 1
        update_zhongshu_state_on_closed_candle(state, candle_payload)

    while pi < plen:
        _, pen = pen_items[pi]
        update_zhongshu_state(state, pen)
        pi += 1

    return state


def build_alive_zhongshu_from_confirmed_pens(
    pens: list[dict],
    *,
    up_to_visible_time: int,
    candles: list[Any] | None = None,
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

    if candles is not None:
        state = replay_zhongshu_state_with_closed_candles(pens=pens, candles=candles, up_to_visible_time=int(t))
    else:
        items: list[tuple[int, dict]] = []
        for p in pens:
            try:
                vt = int(p.get("visible_time") or 0)
            except (ValueError, TypeError):
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

    alive = _alive_from_dict(state.get("alive"))
    if alive is None:
        return None

    start_time = int(alive.start_time)
    end_time = int(alive.end_time)
    zg = float(alive.zg)
    zd = float(alive.zd)
    entry_direction = int(alive.entry_direction)
    formed_time = int(alive.formed_time)
    formed_reason = str(alive.formed_reason or "pen_confirmed")
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
        formed_reason=formed_reason,
    )


def build_dead_zhongshus_from_confirmed_pens(
    pens: list[dict],
    *,
    candles: list[Any] | None = None,
    up_to_visible_time: int | None = None,
) -> list[ZhongshuDead]:
    """
    Forward-growing Zhongshu semantics (append-only dead events):
    - Consumes confirmed pens; when candles are provided, includes closed-candle early-confirm path.
    - Forms with entry pen + next 3 pens (range from the latter 3).
    - Keeps zg/zd fixed after formation.
    - Dies when a new pen is fully above or fully below the zhongshu zone.
    """
    t_limit = int(up_to_visible_time or 0)
    if t_limit <= 0:
        max_pen_time = 0
        for p in pens:
            try:
                max_pen_time = max(max_pen_time, int(p.get("visible_time") or 0))
            except (ValueError, TypeError):
                continue
        max_candle_time = 0
        if candles is not None:
            for c in candles:
                try:
                    max_candle_time = max(max_candle_time, int(getattr(c, "candle_time")))
                except (ValueError, TypeError):
                    continue
        t_limit = max(max_pen_time, max_candle_time)

    items = []
    items = _collect_pen_items(pens=pens, up_to_visible_time=int(t_limit) if t_limit > 0 else None)

    state = init_zhongshu_state()
    out: list[ZhongshuDead] = []

    if candles is None:
        for _, pen in items:
            dead_event, _ = update_zhongshu_state(state, pen)
            if dead_event is not None:
                out.append(dead_event)
        return out

    candle_items = _collect_candle_items(candles=candles, up_to_visible_time=int(t_limit) if t_limit > 0 else None)

    pi = 0
    plen = len(items)
    for candle_time, candle_payload in candle_items:
        while pi < plen and int(items[pi][0]) <= int(candle_time):
            _, pen = items[pi]
            dead_event, _ = update_zhongshu_state(state, pen)
            if dead_event is not None:
                out.append(dead_event)
            pi += 1
        update_zhongshu_state_on_closed_candle(state, candle_payload)

    while pi < plen:
        _, pen = items[pi]
        dead_event, _ = update_zhongshu_state(state, pen)
        if dead_event is not None:
            out.append(dead_event)
        pi += 1

    return out
