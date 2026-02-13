from __future__ import annotations

from typing import Any

from .zhongshu_state_models import ZhongshuAlive, ZhongshuDead, _alive_from_dict
from .zhongshu_state_updates import (
    init_zhongshu_state,
    update_zhongshu_state,
    update_zhongshu_state_on_closed_candle,
)


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
