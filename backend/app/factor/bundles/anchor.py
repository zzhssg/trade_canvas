from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from ..anchor_semantics import build_anchor_history_from_switches, normalize_anchor_ref
from ..plugin_contract import FactorPluginSpec
from ..processor_anchor import AnchorProcessor
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from ...core.schemas import FactorSliceV1
from .common import anchor_ref_strength, build_factor_meta, candidate_anchor_from_pen_head

_ANCHOR_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="anchor",
        event_kind="anchor.switch",
        bucket_name="anchor_switches",
        sort_keys=("visible_time", "switch_time"),
    ),
)


@dataclass(frozen=True)
class AnchorSlicePlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="anchor", depends_on=("pen", "zhongshu"))
    bucket_specs: tuple[SliceBucketSpec, ...] = _ANCHOR_BUCKET_SPECS

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:
        pen_confirmed = list(ctx.buckets.get("pen_confirmed") or [])
        anchor_switches = list(ctx.buckets.get("anchor_switches") or [])
        if not pen_confirmed and not anchor_switches:
            return None

        history_anchors, history_switches = build_anchor_history_from_switches(anchor_switches)
        pen_slice = ctx.snapshots.get("pen")
        pen_head_candidate = (pen_slice.head or {}).get("candidate") if pen_slice is not None else None

        anchor_head_row = ctx.head_rows.get("anchor")
        if anchor_head_row is not None:
            anchor_head = dict(anchor_head_row.head or {})
            current_anchor_ref = normalize_anchor_ref(anchor_head.get("current_anchor_ref"))
        else:
            current_anchor_ref = None
            if history_switches:
                current = history_switches[-1].get("new_anchor")
                if isinstance(current, dict):
                    current_anchor_ref = normalize_anchor_ref(current)
            elif pen_confirmed:
                last_confirmed = pen_confirmed[-1]
                current_anchor_ref = {
                    "kind": "confirmed",
                    "start_time": int(last_confirmed.get("start_time") or 0),
                    "end_time": int(last_confirmed.get("end_time") or 0),
                    "direction": int(last_confirmed.get("direction") or 0),
                }

        candidate_ref, candidate_strength = candidate_anchor_from_pen_head(pen_head_candidate)
        current_strength = anchor_ref_strength(ref=current_anchor_ref, pen_confirmed=pen_confirmed)

        if candidate_ref is not None:
            current_start = int(current_anchor_ref.get("start_time") or 0) if isinstance(current_anchor_ref, dict) else 0
            candidate_start = int(candidate_ref.get("start_time") or 0)
            if current_anchor_ref is None or candidate_start == current_start or candidate_strength > current_strength:
                current_anchor_ref = dict(candidate_ref)

        return FactorSliceV1(
            history={"anchors": history_anchors, "switches": history_switches},
            head={"current_anchor_ref": current_anchor_ref},
            meta=build_factor_meta(ctx=ctx, factor_name="anchor"),
        )


FactorBundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]


def build_bundle() -> FactorBundleBuilders:
    return AnchorProcessor, AnchorSlicePlugin
