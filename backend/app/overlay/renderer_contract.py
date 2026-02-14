from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..factor.plugin_contract import FactorPluginSpec


@dataclass(frozen=True)
class OverlayEventBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


PIVOT_MAJOR_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="pivot",
    event_kind="pivot.major",
    bucket_name="pivot_major",
    sort_keys=("visible_time", "pivot_time"),
)
PIVOT_MINOR_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="pivot",
    event_kind="pivot.minor",
    bucket_name="pivot_minor",
)
ANCHOR_SWITCH_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="anchor",
    event_kind="anchor.switch",
    bucket_name="anchor_switches",
    sort_keys=("visible_time", "switch_time"),
)
PEN_CONFIRMED_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="pen",
    event_kind="pen.confirmed",
    bucket_name="pen_confirmed",
    sort_keys=("visible_time", "start_time"),
)
ZHONGSHU_DEAD_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="zhongshu",
    event_kind="zhongshu.dead",
    bucket_name="zhongshu_dead",
)
SR_SNAPSHOT_BUCKET_SPEC = OverlayEventBucketSpec(
    factor_name="sr",
    event_kind="sr.snapshot",
    bucket_name="sr_snapshots",
    sort_keys=("visible_time", "visible_time"),
)


@dataclass(frozen=True)
class OverlayRenderContext:
    series_id: str
    to_time: int
    cutoff_time: int
    window_candles: int
    candles: list[Any]
    buckets: Mapping[str, list[dict[str, Any]]] = field(default_factory=dict)

    def bucket(self, name: str) -> list[dict[str, Any]]:
        return list(self.buckets.get(name) or [])

    @property
    def pivot_major(self) -> list[dict[str, Any]]:
        return self.bucket("pivot_major")

    @property
    def pivot_minor(self) -> list[dict[str, Any]]:
        return self.bucket("pivot_minor")

    @property
    def pen_confirmed(self) -> list[dict[str, Any]]:
        return self.bucket("pen_confirmed")

    @property
    def zhongshu_dead(self) -> list[dict[str, Any]]:
        return self.bucket("zhongshu_dead")

    @property
    def anchor_switches(self) -> list[dict[str, Any]]:
        return self.bucket("anchor_switches")


@dataclass
class OverlayRenderOutput:
    marker_defs: list[tuple[str, str, int, dict[str, Any]]] = field(default_factory=list)
    polyline_defs: list[tuple[str, int, dict[str, Any]]] = field(default_factory=list)
    pen_points_count: int = 0


class OverlayRendererPlugin(Protocol):
    @property
    def spec(self) -> FactorPluginSpec: ...

    @property
    def bucket_specs(self) -> tuple[OverlayEventBucketSpec, ...]: ...

    def render(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput: ...
