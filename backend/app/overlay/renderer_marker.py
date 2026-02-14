from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor.plugin_contract import FactorPluginSpec
from .renderer_contract import (
    ANCHOR_SWITCH_BUCKET_SPEC,
    PIVOT_MAJOR_BUCKET_SPEC,
    PIVOT_MINOR_BUCKET_SPEC,
    OverlayEventBucketSpec,
    OverlayRenderContext,
    OverlayRenderOutput,
)


@dataclass(frozen=True)
class MarkerOverlayRenderer:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="overlay.marker", depends_on=())
    bucket_specs: tuple[OverlayEventBucketSpec, ...] = (
        PIVOT_MAJOR_BUCKET_SPEC,
        PIVOT_MINOR_BUCKET_SPEC,
        ANCHOR_SWITCH_BUCKET_SPEC,
    )

    def render(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput:
        out = OverlayRenderOutput()
        for level, items, alpha in (
            ("pivot.major", list(ctx.pivot_major), 1.0),
            ("pivot.minor", list(ctx.pivot_minor), 0.6),
        ):
            for pivot in items:
                pivot_time = int(pivot.get("pivot_time") or 0)
                visible_time = int(pivot.get("visible_time") or 0)
                direction = str(pivot.get("direction") or "")
                window = int(pivot.get("window") or 0)
                if pivot_time <= 0 or visible_time <= 0:
                    continue
                if pivot_time < int(ctx.cutoff_time) or pivot_time > int(ctx.to_time):
                    continue
                if direction not in {"support", "resistance"}:
                    continue

                instruction_id = f"{level}:{pivot_time}:{direction}:{window}"
                color = "#ef4444" if direction == "resistance" else "#22c55e"
                if alpha < 1.0:
                    color = f"rgba(239,68,68,{alpha})" if direction == "resistance" else f"rgba(34,197,94,{alpha})"
                out.marker_defs.append(
                    (
                        instruction_id,
                        "marker",
                        int(visible_time),
                        {
                            "type": "marker",
                            "feature": level,
                            "time": int(pivot_time),
                            "position": "aboveBar" if direction == "resistance" else "belowBar",
                            "color": color,
                            "shape": "circle",
                            "text": "",
                            "size": 1.0 if level == "pivot.major" else 0.5,
                        },
                    )
                )

        for switch in list(ctx.anchor_switches):
            switch_time = int(switch.get("switch_time") or 0)
            if switch_time <= 0:
                continue
            if switch_time < int(ctx.cutoff_time) or switch_time > int(ctx.to_time):
                continue
            reason = str(switch.get("reason") or "switch")
            raw_new_anchor = switch.get("new_anchor")
            new_anchor = raw_new_anchor if isinstance(raw_new_anchor, dict) else {}
            anchor_direction = int(new_anchor.get("direction") or 0)
            position = "belowBar" if anchor_direction >= 0 else "aboveBar"
            shape = "arrowUp" if anchor_direction >= 0 else "arrowDown"
            instruction_id = f"anchor.switch:{switch_time}:{anchor_direction}:{reason}"
            out.marker_defs.append(
                (
                    instruction_id,
                    "marker",
                    int(switch_time),
                    {
                        "type": "marker",
                        "feature": "anchor.switch",
                        "time": int(switch_time),
                        "position": position,
                        "color": "#f59e0b",
                        "shape": shape,
                        "text": "A",
                        "size": 1.0,
                    },
                )
            )
        return out
