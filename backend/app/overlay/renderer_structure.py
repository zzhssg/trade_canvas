from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor.anchor_semantics import build_anchor_history_from_switches, normalize_anchor_ref
from ..factor.plugin_contract import FactorPluginSpec
from ..factor.slices import build_pen_head_candidate, build_pen_head_preview
from ..factor.zhongshu import build_alive_zhongshu_from_confirmed_pens
from .renderer_contract import OverlayEventBucketSpec, OverlayRenderContext, OverlayRenderOutput
from .renderer_structure_helpers import (
    append_polyline,
    build_pen_indexes,
    render_alive_zhongshu,
    render_dead_zhongshu,
)


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
        pen_lookup, pen_latest_by_start_dir, pen_latest_by_start = build_pen_indexes(pens=pens)

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

        render_dead_zhongshu(
            out=out,
            zhongshu_dead=list(ctx.zhongshu_dead),
            cutoff_time=int(ctx.cutoff_time),
            to_time=int(ctx.to_time),
            pen_latest_by_start=pen_latest_by_start,
        )
        render_alive_zhongshu(
            out=out,
            alive=alive,
            to_time=int(ctx.to_time),
        )

        history_anchors, history_switches = build_anchor_history_from_switches(list(ctx.anchor_switches))
        current_ref: dict[str, Any] | None = None
        if history_switches:
            current = history_switches[-1].get("new_anchor")
            if isinstance(current, dict):
                current_ref = normalize_anchor_ref(current)
        elif last_confirmed is not None:
            current_ref = {
                "kind": "confirmed",
                "start_time": int(last_confirmed.get("start_time") or 0),
                "end_time": int(last_confirmed.get("end_time") or 0),
                "direction": int(last_confirmed.get("direction") or 0),
            }
            current_ref = normalize_anchor_ref(current_ref)

        def anchor_ref_strength(ref: dict[str, Any] | None) -> float:
            if not isinstance(ref, dict):
                return -1.0
            start_time = int(ref.get("start_time") or 0)
            direction = int(ref.get("direction") or 0)
            if start_time <= 0 or direction not in {-1, 1}:
                return -1.0
            match = pen_latest_by_start_dir.get((start_time, direction))
            if match is None:
                return -1.0
            return abs(float(match.get("end_price") or 0.0) - float(match.get("start_price") or 0.0))

        candidate_ref: dict[str, Any] | None = None
        candidate_strength = -1.0
        if isinstance(pen_candidate, dict):
            candidate_ref = normalize_anchor_ref(
                {
                    "kind": "candidate",
                    "start_time": int(pen_candidate.get("start_time") or 0),
                    "end_time": int(pen_candidate.get("end_time") or 0),
                    "direction": int(pen_candidate.get("direction") or 0),
                }
            )
            candidate_strength = abs(
                float(pen_candidate.get("end_price") or 0.0) - float(pen_candidate.get("start_price") or 0.0)
            )

        if candidate_ref is not None:
            current_start = int(current_ref.get("start_time") or 0) if isinstance(current_ref, dict) else 0
            candidate_start = int(candidate_ref.get("start_time") or 0)
            current_strength = anchor_ref_strength(current_ref)
            if current_ref is None or candidate_start == current_start or candidate_strength > current_strength:
                current_ref = dict(candidate_ref)

        def resolve_points(ref: dict[str, Any] | None) -> tuple[list[dict[str, Any]], bool]:
            if not ref:
                return [], False
            kind = str(ref.get("kind") or "")
            start_time = int(ref.get("start_time") or 0)
            end_time = int(ref.get("end_time") or 0)
            direction = int(ref.get("direction") or 0)
            if start_time <= 0 or end_time <= 0:
                return [], False
            if kind == "candidate" and isinstance(pen_candidate, dict):
                if (
                    int(pen_candidate.get("start_time") or 0) == start_time
                    and int(pen_candidate.get("end_time") or 0) == end_time
                    and int(pen_candidate.get("direction") or 0) == direction
                ):
                    return (
                        [
                            {"time": start_time, "value": float(pen_candidate.get("start_price") or 0.0)},
                            {"time": end_time, "value": float(pen_candidate.get("end_price") or 0.0)},
                        ],
                        True,
                    )
            match = pen_lookup.get((start_time, end_time, direction))
            if match is None:
                match = pen_latest_by_start_dir.get((start_time, direction))
            if match is None:
                return [], False
            return (
                [
                    {"time": int(match.get("start_time") or 0), "value": float(match.get("start_price") or 0.0)},
                    {"time": int(match.get("end_time") or 0), "value": float(match.get("end_price") or 0.0)},
                ],
                False,
            )

        anchor_points, anchor_from_candidate = resolve_points(current_ref)
        if anchor_points:
            append_polyline(
                out=out,
                instruction_id="anchor.current",
                visible_time=int(ctx.to_time),
                feature="anchor.current",
                points=anchor_points,
                color="#f59e0b",
                line_style="dashed" if anchor_from_candidate else None,
            )

        current_pointer_start = int(current_ref.get("start_time") or 0) if isinstance(current_ref, dict) else 0
        for idx, anchor_ref in enumerate(history_anchors):
            if current_pointer_start > 0 and int(anchor_ref.get("start_time") or 0) == current_pointer_start:
                continue
            history_points, _ = resolve_points(anchor_ref)
            if not history_points:
                continue
            switch_payload = history_switches[idx]
            switch_time = int(switch_payload.get("switch_time") or int(ctx.to_time))
            instruction_id = (
                f"anchor.history:{switch_time}:{int(anchor_ref.get('start_time') or 0)}:"
                f"{int(anchor_ref.get('end_time') or 0)}:{int(anchor_ref.get('direction') or 0)}"
            )
            append_polyline(
                out=out,
                instruction_id=instruction_id,
                visible_time=max(1, switch_time),
                feature="anchor.history",
                points=history_points,
                color="rgba(59,130,246,0.55)",
                line_width=1,
            )

        if isinstance(pen_extending, dict):
            append_polyline(
                out=out,
                instruction_id="pen.extending",
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
            append_polyline(
                out=out,
                instruction_id="pen.candidate",
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
