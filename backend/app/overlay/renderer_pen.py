from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor.plugin_contract import FactorPluginSpec
from .renderer_contract import OverlayEventBucketSpec, OverlayRenderContext, OverlayRenderOutput


@dataclass(frozen=True)
class PenOverlayRenderer:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="overlay.pen", depends_on=())
    bucket_specs: tuple[OverlayEventBucketSpec, ...] = (
        OverlayEventBucketSpec(
            factor_name="pen",
            event_kind="pen.confirmed",
            bucket_name="pen_confirmed",
            sort_keys=("visible_time", "start_time"),
        ),
    )

    def render(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput:
        out = OverlayRenderOutput()
        pens = sorted(
            (dict(item) for item in ctx.pen_confirmed),
            key=lambda data: (int(data.get("start_time") or 0), int(data.get("visible_time") or 0)),
        )
        points: list[dict[str, Any]] = []
        for item in pens:
            start_time = int(item.get("start_time") or 0)
            end_time = int(item.get("end_time") or 0)
            start_price = float(item.get("start_price") or 0.0)
            end_price = float(item.get("end_price") or 0.0)
            if start_time <= 0 or end_time <= 0:
                continue
            if end_time < int(ctx.cutoff_time) or start_time > int(ctx.to_time):
                continue
            if not points or points[-1].get("time") != start_time:
                points.append({"time": start_time, "value": start_price})
            points.append({"time": end_time, "value": end_price})

        out.pen_points_count = int(len(points))
        if points:
            out.polyline_defs.append(
                (
                    "pen.confirmed",
                    int(ctx.to_time),
                    {
                        "type": "polyline",
                        "feature": "pen.confirmed",
                        "points": list(points),
                        "color": "#ffffff",
                        "lineWidth": 2,
                    },
                )
            )
        return out
