from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor.plugin_contract import FactorPluginSpec
from .renderer_contract import SR_SNAPSHOT_BUCKET_SPEC, OverlayEventBucketSpec, OverlayRenderContext, OverlayRenderOutput
from .renderer_structure_helpers import PolylineRequest, append_polyline


@dataclass(frozen=True)
class SrOverlayRenderer:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="overlay.sr",
        depends_on=("overlay.structure",),
    )
    bucket_specs: tuple[OverlayEventBucketSpec, ...] = (
        SR_SNAPSHOT_BUCKET_SPEC,
    )

    def render(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput:
        out = OverlayRenderOutput()
        snapshots = list(ctx.bucket("sr_snapshots"))
        if not snapshots:
            return out

        latest = snapshots[-1] if snapshots else {}
        levels = list(latest.get("levels") or []) if isinstance(latest, dict) else []
        for level in levels:
            if not isinstance(level, dict):
                continue
            request = self._build_level_polyline(level=level, ctx=ctx)
            if request is None:
                continue
            append_polyline(out=out, request=request)
        return out

    def _build_level_polyline(self, *, level: dict[str, Any], ctx: OverlayRenderContext) -> PolylineRequest | None:
        price = float(level.get("price") or 0.0)
        if price <= 0:
            return None

        status = str(level.get("status") or "")
        level_type = str(level.get("level_type") or level.get("type") or "")
        start_time = int(level.get("first_time") or level.get("second_time") or level.get("last_time") or 0)
        end_time = int(level.get("death_time") or 0) if status == "broken" else int(ctx.to_time)
        if end_time <= 0:
            end_time = int(ctx.to_time)
        if start_time <= 0:
            start_time = int(level.get("last_time") or 0)
        if start_time <= 0:
            return None

        if end_time < int(ctx.cutoff_time) or start_time > int(ctx.to_time):
            return None
        start_time = max(int(start_time), int(ctx.cutoff_time))
        end_time = min(int(end_time), int(ctx.to_time))
        if end_time < start_time:
            return None

        is_resistance = level_type == "resistance"
        feature = "sr.broken" if status == "broken" else "sr.active"
        color = "#ef4444" if is_resistance else "#22c55e"
        line_style: str | None = None
        line_width = 2
        if status == "broken":
            color = "rgba(148,163,184,0.6)"
            line_style = "dashed"
            line_width = 1

        instruction_id = (
            f"sr.{feature}:{status}:{level_type}:{price:.8f}:"
            f"{int(start_time)}:{int(end_time)}"
        )
        return PolylineRequest(
            instruction_id=instruction_id,
            visible_time=int(ctx.to_time),
            feature=feature,
            points=[
                {"time": int(start_time), "value": float(price)},
                {"time": int(end_time), "value": float(price)},
            ],
            color=color,
            line_width=int(line_width),
            line_style=line_style,
        )
