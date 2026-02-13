from __future__ import annotations

from typing import Any

from .zhongshu_state_models import (
    ZhongshuDead,
    _alive_from_dict,
    _alive_to_dict,
    _as_range,
    _pending_from_dict,
    _pending_to_dict,
)
from .zhongshu_state_transitions import (
    _build_pending_from_tail,
    _is_same_side_outside,
    _try_form_from_pending_with_confirmed,
    _try_form_from_pending_with_cross,
)


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
