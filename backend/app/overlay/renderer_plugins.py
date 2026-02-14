from __future__ import annotations

from .renderer_bucketing import build_overlay_event_bucket_config, collect_overlay_event_buckets
from .renderer_contract import (
    OverlayEventBucketSpec,
    OverlayRenderContext,
    OverlayRenderOutput,
    OverlayRendererPlugin,
)
from .renderer_marker import MarkerOverlayRenderer
from .renderer_pen import PenOverlayRenderer
from .renderer_sr import SrOverlayRenderer
from .renderer_structure import StructureOverlayRenderer


def build_default_overlay_render_plugins() -> tuple[OverlayRendererPlugin, ...]:
    return (
        MarkerOverlayRenderer(),
        PenOverlayRenderer(),
        StructureOverlayRenderer(),
        SrOverlayRenderer(),
    )


__all__ = [
    "MarkerOverlayRenderer",
    "OverlayEventBucketSpec",
    "OverlayRenderContext",
    "OverlayRenderOutput",
    "OverlayRendererPlugin",
    "PenOverlayRenderer",
    "SrOverlayRenderer",
    "StructureOverlayRenderer",
    "build_default_overlay_render_plugins",
    "build_overlay_event_bucket_config",
    "collect_overlay_event_buckets",
]
