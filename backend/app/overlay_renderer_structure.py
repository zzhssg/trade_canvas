from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .anchor_semantics import build_anchor_history_from_switches
from .factor_plugin_contract import FactorPluginSpec
from .factor_slices import build_pen_head_candidate, build_pen_head_preview
from .overlay_renderer_contract import OverlayEventBucketSpec, OverlayRenderContext, OverlayRenderOutput
from .zhongshu import build_alive_zhongshu_from_confirmed_pens


@dataclass(frozen=True)
class StructureOverlayRenderer:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="overlay.structure",
        depends_on=("overlay.pen",),
    )
    bucket_specs: tuple[OverlayEventBucketSpec, ...] = (
        OverlayEventBucketSpec(
            factor_name="pivot",
            event_kind="pivot.major",
            bucket_name="pivot_major",
            sort_keys=("visible_time", "pivot_time"),
        ),
        OverlayEventBucketSpec(
            factor_name="pen",
            event_kind="pen.confirmed",
            bucket_name="pen_confirmed",
            sort_keys=("visible_time", "start_time"),
        ),
        OverlayEventBucketSpec(
            factor_name="zhongshu",
            event_kind="zhongshu.dead",
            bucket_name="zhongshu_dead",
        ),
        OverlayEventBucketSpec(
            factor_name="anchor",
            event_kind="anchor.switch",
            bucket_name="anchor_switches",
            sort_keys=("visible_time", "switch_time"),
        ),
    )

    def render(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput:
        out = OverlayRenderOutput()
        pens = sorted(
            (dict(item) for item in ctx.pen_confirmed),
            key=lambda data: (int(data.get("visible_time") or 0), int(data.get("start_time") or 0)),
        )
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

        last_confirmed = pens[-1] if pens else None
        preview = build_pen_head_preview(
            candles=ctx.candles,
            major_pivots=list(ctx.pivot_major),
            aligned_time=int(ctx.to_time),
        )
        pen_extending = preview.get("extending") if isinstance(preview.get("extending"), dict) else None
        pen_candidate = preview.get("candidate") if isinstance(preview.get("candidate"), dict) else None
        if pen_candidate is None:
            pen_candidate = build_pen_head_candidate(
                candles=ctx.candles,
                last_confirmed=last_confirmed,
                aligned_time=int(ctx.to_time),
            )

        if pens:
            try:
                alive = build_alive_zhongshu_from_confirmed_pens(
                    pens,
                    up_to_visible_time=int(ctx.to_time),
                    candles=ctx.candles,
                )
            except Exception:
                alive = None
        else:
            alive = None

        def add_polyline(
            instruction_id: str,
            *,
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

        def zhongshu_border_color(*, is_alive: bool, entry_direction: int) -> str:
            if is_alive:
                return "rgba(22,163,74,0.72)" if entry_direction >= 0 else "rgba(220,38,38,0.72)"
            return "rgba(74,222,128,0.58)" if entry_direction >= 0 else "rgba(248,113,113,0.58)"

        def resolve_dead_entry_direction(zhongshu: dict[str, Any]) -> int:
            try:
                raw = int(zhongshu.get("entry_direction") or 0)
            except Exception:
                raw = 0
            if raw in {-1, 1}:
                return int(raw)
            start_time = int(zhongshu.get("start_time") or 0)
            if start_time > 0:
                matched = pen_latest_by_start.get(start_time)
                if isinstance(matched, dict):
                    try:
                        direction = int(matched.get("direction") or 0)
                    except Exception:
                        direction = 0
                    if direction in {-1, 1}:
                        return int(direction)
            return 1

        for zhongshu in list(ctx.zhongshu_dead):
            start_time = int(zhongshu.get("start_time") or 0)
            end_time = int(zhongshu.get("end_time") or 0)
            zg = float(zhongshu.get("zg") or 0.0)
            zd = float(zhongshu.get("zd") or 0.0)
            visible_time = int(zhongshu.get("visible_time") or 0)
            entry_direction = resolve_dead_entry_direction(zhongshu)
            if start_time <= 0 or end_time <= 0 or visible_time <= 0:
                continue
            if end_time < int(ctx.cutoff_time) or start_time > int(ctx.to_time):
                continue
            base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
            border_color = zhongshu_border_color(is_alive=False, entry_direction=entry_direction)
            add_polyline(
                f"{base_id}:top",
                visible_time=visible_time,
                feature="zhongshu.dead",
                points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
                color=border_color,
                entry_direction=entry_direction,
            )
            add_polyline(
                f"{base_id}:bottom",
                visible_time=visible_time,
                feature="zhongshu.dead",
                points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
                color=border_color,
                entry_direction=entry_direction,
            )

        if alive is not None and int(alive.visible_time) == int(ctx.to_time):
            start_time = int(alive.start_time)
            end_time = int(alive.end_time)
            zg = float(alive.zg)
            zd = float(alive.zd)
            entry_direction = int(alive.entry_direction) if int(alive.entry_direction) in {-1, 1} else 1
            border_color = zhongshu_border_color(is_alive=True, entry_direction=entry_direction)
            add_polyline(
                "zhongshu.alive:top",
                visible_time=int(ctx.to_time),
                feature="zhongshu.alive",
                points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
                color=border_color,
                entry_direction=entry_direction,
            )
            add_polyline(
                "zhongshu.alive:bottom",
                visible_time=int(ctx.to_time),
                feature="zhongshu.alive",
                points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
                color=border_color,
                entry_direction=entry_direction,
            )

        history_anchors, history_switches = build_anchor_history_from_switches(list(ctx.anchor_switches))
        current_ref: dict[str, Any] | None = None
        if history_switches:
            current = history_switches[-1].get("new_anchor")
            if isinstance(current, dict):
                current_ref = current
        elif last_confirmed is not None:
            current_ref = {
                "kind": "confirmed",
                "start_time": int(last_confirmed.get("start_time") or 0),
                "end_time": int(last_confirmed.get("end_time") or 0),
                "direction": int(last_confirmed.get("direction") or 0),
            }

        def resolve_points(ref: dict[str, Any] | None) -> list[dict[str, Any]]:
            if not ref:
                return []
            kind = str(ref.get("kind") or "")
            start_time = int(ref.get("start_time") or 0)
            end_time = int(ref.get("end_time") or 0)
            direction = int(ref.get("direction") or 0)
            if start_time <= 0 or end_time <= 0:
                return []
            if kind == "candidate" and isinstance(pen_candidate, dict):
                if (
                    int(pen_candidate.get("start_time") or 0) == start_time
                    and int(pen_candidate.get("end_time") or 0) == end_time
                    and int(pen_candidate.get("direction") or 0) == direction
                ):
                    return [
                        {"time": start_time, "value": float(pen_candidate.get("start_price") or 0.0)},
                        {"time": end_time, "value": float(pen_candidate.get("end_price") or 0.0)},
                    ]
            match = pen_lookup.get((start_time, end_time, direction))
            if match is None:
                match = pen_latest_by_start_dir.get((start_time, direction))
            if match is None:
                return []
            return [
                {"time": int(match.get("start_time") or 0), "value": float(match.get("start_price") or 0.0)},
                {"time": int(match.get("end_time") or 0), "value": float(match.get("end_price") or 0.0)},
            ]

        anchor_points = resolve_points(current_ref)
        if anchor_points:
            add_polyline(
                "anchor.current",
                visible_time=int(ctx.to_time),
                feature="anchor.current",
                points=anchor_points,
                color="#f59e0b",
            )

        current_pointer_start = int(current_ref.get("start_time") or 0) if isinstance(current_ref, dict) else 0
        for idx, anchor_ref in enumerate(history_anchors):
            if current_pointer_start > 0 and int(anchor_ref.get("start_time") or 0) == current_pointer_start:
                continue
            history_points = resolve_points(anchor_ref)
            if not history_points:
                continue
            switch_payload = history_switches[idx]
            switch_time = int(switch_payload.get("switch_time") or int(ctx.to_time))
            instruction_id = (
                f"anchor.history:{switch_time}:{int(anchor_ref.get('start_time') or 0)}:"
                f"{int(anchor_ref.get('end_time') or 0)}:{int(anchor_ref.get('direction') or 0)}"
            )
            add_polyline(
                instruction_id,
                visible_time=max(1, switch_time),
                feature="anchor.history",
                points=history_points,
                color="rgba(59,130,246,0.55)",
                line_width=1,
            )

        if isinstance(pen_extending, dict):
            add_polyline(
                "pen.extending",
                visible_time=int(ctx.to_time),
                feature="pen.extending",
                points=[
                    {"time": int(pen_extending.get("start_time") or 0), "value": float(pen_extending.get("start_price") or 0.0)},
                    {"time": int(pen_extending.get("end_time") or 0), "value": float(pen_extending.get("end_price") or 0.0)},
                ],
                color="#ffffff",
                line_style="dashed",
            )

        if isinstance(pen_candidate, dict):
            add_polyline(
                "pen.candidate",
                visible_time=int(ctx.to_time),
                feature="pen.candidate",
                points=[
                    {"time": int(pen_candidate.get("start_time") or 0), "value": float(pen_candidate.get("start_price") or 0.0)},
                    {"time": int(pen_candidate.get("end_time") or 0), "value": float(pen_candidate.get("end_price") or 0.0)},
                ],
                color="#ffffff",
                line_style="dashed",
            )

        return out
