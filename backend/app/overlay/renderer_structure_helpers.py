from __future__ import annotations

from typing import Any

from .renderer_contract import OverlayRenderOutput


def append_polyline(
    *,
    out: OverlayRenderOutput,
    instruction_id: str,
    visible_time: int,
    feature: str,
    points: list[dict[str, Any]],
    color: str,
    line_width: int = 2,
    line_style: str | None = None,
    entry_direction: int | None = None,
) -> None:
    if len(points) < 2:
        return
    payload: dict[str, Any] = {
        "type": "polyline",
        "feature": feature,
        "points": points,
        "color": color,
        "lineWidth": int(line_width),
    }
    if line_style:
        payload["lineStyle"] = str(line_style)
    if entry_direction in {-1, 1}:
        payload["entryDirection"] = int(entry_direction)
    out.polyline_defs.append((instruction_id, int(visible_time), payload))


def build_pen_indexes(
    *,
    pens: list[dict[str, Any]],
) -> tuple[
    dict[tuple[int, int, int], dict[str, Any]],
    dict[tuple[int, int], dict[str, Any]],
    dict[int, dict[str, Any]],
]:
    pen_lookup: dict[tuple[int, int, int], dict[str, Any]] = {}
    pen_latest_by_start_dir: dict[tuple[int, int], dict[str, Any]] = {}
    pen_latest_by_start: dict[int, dict[str, Any]] = {}
    for pen in pens:
        start_time = int(pen.get("start_time") or 0)
        end_time = int(pen.get("end_time") or 0)
        direction = int(pen.get("direction") or 0)
        pen_lookup[(start_time, end_time, direction)] = pen
        pointer_key = (start_time, direction)
        prev = pen_latest_by_start_dir.get(pointer_key)
        if prev is None or int(prev.get("end_time") or 0) <= end_time:
            pen_latest_by_start_dir[pointer_key] = pen
        prev_start = pen_latest_by_start.get(start_time)
        if prev_start is None or int(prev_start.get("end_time") or 0) <= end_time:
            pen_latest_by_start[start_time] = pen
    return pen_lookup, pen_latest_by_start_dir, pen_latest_by_start


def _zhongshu_border_color(*, is_alive: bool, entry_direction: int) -> str:
    if is_alive:
        return "rgba(22,163,74,0.72)" if entry_direction >= 0 else "rgba(220,38,38,0.72)"
    return "rgba(74,222,128,0.58)" if entry_direction >= 0 else "rgba(248,113,113,0.58)"


def _resolve_dead_entry_direction(
    *,
    zhongshu: dict[str, Any],
    pen_latest_by_start: dict[int, dict[str, Any]],
) -> int:
    try:
        raw = int(zhongshu.get("entry_direction") or 0)
    except (ValueError, TypeError):
        raw = 0
    if raw in {-1, 1}:
        return int(raw)
    start_time = int(zhongshu.get("start_time") or 0)
    if start_time > 0:
        matched = pen_latest_by_start.get(start_time)
        if isinstance(matched, dict):
            try:
                direction = int(matched.get("direction") or 0)
            except (ValueError, TypeError):
                direction = 0
            if direction in {-1, 1}:
                return int(direction)
    return 1


def render_dead_zhongshu(
    *,
    out: OverlayRenderOutput,
    zhongshu_dead: list[dict[str, Any]],
    cutoff_time: int,
    to_time: int,
    pen_latest_by_start: dict[int, dict[str, Any]],
) -> None:
    for zhongshu in zhongshu_dead:
        start_time = int(zhongshu.get("start_time") or 0)
        end_time = int(zhongshu.get("end_time") or 0)
        zg = float(zhongshu.get("zg") or 0.0)
        zd = float(zhongshu.get("zd") or 0.0)
        visible_time = int(zhongshu.get("visible_time") or 0)
        entry_direction = _resolve_dead_entry_direction(
            zhongshu=zhongshu,
            pen_latest_by_start=pen_latest_by_start,
        )
        if start_time <= 0 or end_time <= 0 or visible_time <= 0:
            continue
        if end_time < int(cutoff_time) or start_time > int(to_time):
            continue
        base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
        border_color = _zhongshu_border_color(
            is_alive=False,
            entry_direction=entry_direction,
        )
        append_polyline(
            out=out,
            instruction_id=f"{base_id}:top",
            visible_time=visible_time,
            feature="zhongshu.dead",
            points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
            color=border_color,
            entry_direction=entry_direction,
        )
        append_polyline(
            out=out,
            instruction_id=f"{base_id}:bottom",
            visible_time=visible_time,
            feature="zhongshu.dead",
            points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
            color=border_color,
            entry_direction=entry_direction,
        )


def render_alive_zhongshu(
    *,
    out: OverlayRenderOutput,
    alive: Any | None,
    to_time: int,
) -> None:
    if alive is None or int(alive.visible_time) != int(to_time):
        return
    start_time = int(alive.start_time)
    end_time = int(alive.end_time)
    zg = float(alive.zg)
    zd = float(alive.zd)
    entry_direction = int(alive.entry_direction) if int(alive.entry_direction) in {-1, 1} else 1
    border_color = _zhongshu_border_color(
        is_alive=True,
        entry_direction=entry_direction,
    )
    append_polyline(
        out=out,
        instruction_id="zhongshu.alive:top",
        visible_time=int(to_time),
        feature="zhongshu.alive",
        points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
        color=border_color,
        entry_direction=entry_direction,
    )
    append_polyline(
        out=out,
        instruction_id="zhongshu.alive:bottom",
        visible_time=int(to_time),
        feature="zhongshu.alive",
        points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
        color=border_color,
        entry_direction=entry_direction,
    )
