from __future__ import annotations

from typing import Any

from .slices import build_pen_head_preview
from .zhongshu import build_alive_zhongshu_from_confirmed_pens


def _major_pivots_for_head(effective_pivots: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for point in effective_pivots:
        if isinstance(point, dict):
            out.append(
                {
                    "pivot_time": int(point.get("pivot_time") or 0),
                    "pivot_price": float(point.get("pivot_price") or 0.0),
                    "direction": str(point.get("direction") or ""),
                    "visible_time": int(point.get("visible_time") or 0),
                }
            )
            continue
        out.append(
            {
                "pivot_time": int(getattr(point, "pivot_time", 0) or 0),
                "pivot_price": float(getattr(point, "pivot_price", 0.0) or 0.0),
                "direction": str(getattr(point, "direction", "") or ""),
                "visible_time": int(getattr(point, "visible_time", 0) or 0),
            }
        )
    return out


def build_pen_head_snapshot(
    *,
    confirmed_pens: list[dict[str, Any]],
    effective_pivots: list[Any],
    candles: list[Any],
    aligned_time: int,
) -> dict[str, Any] | None:
    if not confirmed_pens:
        return None
    preview = build_pen_head_preview(
        candles=candles,
        major_pivots=_major_pivots_for_head(effective_pivots),
        aligned_time=int(aligned_time),
    )
    pen_head: dict[str, Any] = {}
    for key in ("extending", "candidate"):
        value = preview.get(key)
        if isinstance(value, dict):
            pen_head[key] = value
    return pen_head


def _alive_payload_from_state(*, alive_state: Any, aligned_time: int) -> list[dict[str, Any]] | None:
    if isinstance(alive_state, list):
        out = []
        for item in alive_state:
            if not isinstance(item, dict):
                continue
            out.append(dict(item))
        return out if out else None
    if not isinstance(alive_state, dict):
        return None
    return [
        {
            "start_time": int(alive_state.get("start_time") or 0),
            "end_time": int(alive_state.get("end_time") or 0),
            "zg": float(alive_state.get("zg") or 0.0),
            "zd": float(alive_state.get("zd") or 0.0),
            "entry_direction": int(alive_state.get("entry_direction") or 1),
            "formed_time": int(alive_state.get("formed_time") or 0),
            "formed_reason": str(alive_state.get("formed_reason") or "pen_confirmed"),
            "death_time": None,
            "visible_time": int(aligned_time),
        }
    ]


def build_zhongshu_alive_head(
    *,
    zhongshu_state: dict[str, Any],
    confirmed_pens: list[dict[str, Any]],
    candles: list[Any],
    aligned_time: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if confirmed_pens:
        out["alive"] = []

    alive_state = zhongshu_state.get("alive")
    from_state = _alive_payload_from_state(alive_state=alive_state, aligned_time=int(aligned_time))
    if from_state is not None:
        out["alive"] = from_state
        return out

    if not confirmed_pens:
        return out

    alive = build_alive_zhongshu_from_confirmed_pens(
        confirmed_pens,
        up_to_visible_time=int(aligned_time),
        candles=candles,
    )
    if alive is None or int(alive.visible_time) != int(aligned_time):
        return out
    out["alive"] = [
        {
            "start_time": int(alive.start_time),
            "end_time": int(alive.end_time),
            "zg": float(alive.zg),
            "zd": float(alive.zd),
            "entry_direction": int(alive.entry_direction),
            "formed_time": int(alive.formed_time),
            "formed_reason": str(alive.formed_reason),
            "death_time": None,
            "visible_time": int(alive.visible_time),
        }
    ]
    return out
