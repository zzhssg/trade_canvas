from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZhongshuDead:
    start_time: int
    end_time: int
    zg: float  # upper bound
    zd: float  # lower bound
    formed_time: int
    death_time: int
    visible_time: int


@dataclass(frozen=True)
class ZhongshuAlive:
    start_time: int
    end_time: int
    zg: float  # upper bound
    zd: float  # lower bound
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


def build_alive_zhongshu_from_confirmed_pens(
    pens: list[dict],
    *,
    up_to_visible_time: int,
) -> ZhongshuAlive | None:
    """
    Compute the t-time alive zhongshu snapshot (head-only):
    - Uses only confirmed pens with visible_time<=t (no future function).
    - Replays the same conservative intersection semantics as build_dead_zhongshus_from_confirmed_pens.
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

    alive: dict | None = None

    def try_form(window: list[dict]) -> dict | None:
        if len(window) < 3:
            return None
        ranges = [_as_range(p) for p in window[-3:]]
        if any(r is None for r in ranges):
            return None
        lo = max(r[0] for r in ranges if r is not None)
        hi = min(r[1] for r in ranges if r is not None)
        if lo > hi:
            return None
        third = window[-1]
        formed_time = int(third.get("visible_time") or 0)
        if formed_time <= 0:
            return None
        start_time = int(window[-3].get("start_time") or 0)
        end_time = int(third.get("end_time") or 0)
        if start_time <= 0 or end_time <= 0:
            return None
        return {
            "start_time": start_time,
            "end_time": end_time,
            "zg": float(hi),
            "zd": float(lo),
            "formed_time": formed_time,
            "last_seen_visible_time": formed_time,
        }

    confirmed: list[dict] = []
    for visible_time, pen in items:
        confirmed.append(pen)
        r = _as_range(pen)
        if r is None:
            continue

        if alive is None:
            alive = try_form(confirmed)
            continue

        lo = float(alive["zd"])
        hi = float(alive["zg"])
        nlo = max(lo, float(r[0]))
        nhi = min(hi, float(r[1]))

        if nlo <= nhi:
            alive["zd"] = float(nlo)
            alive["zg"] = float(nhi)
            try:
                alive["end_time"] = max(int(alive.get("end_time") or 0), int(pen.get("end_time") or 0))
            except Exception:
                pass
            alive["last_seen_visible_time"] = int(visible_time)
            continue

        # Alive dies at current pen visible_time; clear and allow immediate reform.
        alive = None
        alive = try_form(confirmed)

    if alive is None:
        return None

    try:
        start_time = int(alive.get("start_time") or 0)
        end_time = int(alive.get("end_time") or 0)
        zg = float(alive.get("zg") or 0.0)
        zd = float(alive.get("zd") or 0.0)
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
        formed_time=formed_time,
        visible_time=int(t),
    )


def build_dead_zhongshus_from_confirmed_pens(pens: list[dict]) -> list[ZhongshuDead]:
    """
    Minimal Zhongshu semantics (append-only dead events):
    - Consumes confirmed pens (history only).
    - Forms when the last 3 pen ranges overlap (intersection non-empty).
    - While alive, intersection is updated by intersecting with each new pen range.
    - Dies when intersection becomes empty, visible at the current pen's visible_time.

    This is intentionally conservative and deterministic; it avoids future function by using only confirmed pens.
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

    alive: dict | None = None
    out: list[ZhongshuDead] = []

    def try_form(window: list[dict]) -> dict | None:
        if len(window) < 3:
            return None
        ranges = [_as_range(p) for p in window[-3:]]
        if any(r is None for r in ranges):
            return None
        lo = max(r[0] for r in ranges if r is not None)
        hi = min(r[1] for r in ranges if r is not None)
        if lo > hi:
            return None
        third = window[-1]
        formed_time = int(third.get("visible_time") or 0)
        if formed_time <= 0:
            return None
        start_time = int(window[-3].get("start_time") or 0)
        end_time = int(third.get("end_time") or 0)
        if start_time <= 0 or end_time <= 0:
            return None
        return {
            "start_time": start_time,
            "end_time": end_time,
            "zg": float(hi),
            "zd": float(lo),
            "formed_time": formed_time,
            "last_seen_visible_time": formed_time,
        }

    # Keep a rolling list of confirmed pens to enable "form after death".
    confirmed: list[dict] = []
    for visible_time, pen in items:
        confirmed.append(pen)
        r = _as_range(pen)
        if r is None:
            continue

        if alive is None:
            alive = try_form(confirmed)
            continue

        lo = float(alive["zd"])
        hi = float(alive["zg"])
        nlo = max(lo, float(r[0]))
        nhi = min(hi, float(r[1]))

        if nlo <= nhi:
            alive["zd"] = float(nlo)
            alive["zg"] = float(nhi)
            try:
                alive["end_time"] = max(int(alive.get("end_time") or 0), int(pen.get("end_time") or 0))
            except Exception:
                pass
            alive["last_seen_visible_time"] = int(visible_time)
            continue

        # Alive dies at current pen visible_time.
        out.append(
            ZhongshuDead(
                start_time=int(alive["start_time"]),
                end_time=int(alive.get("end_time") or 0),
                zg=float(alive["zg"]),
                zd=float(alive["zd"]),
                formed_time=int(alive["formed_time"]),
                death_time=int(visible_time),
                visible_time=int(visible_time),
            )
        )
        alive = None

        # After death, allow immediate reform using the latest window.
        alive = try_form(confirmed)

    return out
