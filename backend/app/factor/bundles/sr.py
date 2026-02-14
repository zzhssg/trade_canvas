from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..plugin_contract import FactorPluginSpec
from ..processor_sr import SrProcessor
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from ...core.schemas import FactorSliceV1
from .common import build_factor_meta

_SR_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="sr",
        event_kind="sr.snapshot",
        bucket_name="sr_snapshots",
        sort_keys=("visible_time", "visible_time"),
    ),
)


@dataclass(frozen=True)
class SrSlicePlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="sr", depends_on=("pivot",))
    bucket_specs: tuple[SliceBucketSpec, ...] = _SR_BUCKET_SPECS

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:
        snapshots = list(ctx.buckets.get("sr_snapshots") or [])
        head_payload: dict[str, Any] = {}
        head_row = ctx.head_rows.get("sr")
        if head_row is not None:
            head_payload = dict(head_row.head or {})
        elif snapshots:
            latest = snapshots[-1]
            head_payload = {
                "algorithm": str(latest.get("algorithm") or ""),
                "levels": list(latest.get("levels") or []),
                "pivots": list(latest.get("pivots") or []),
            }

        if not snapshots and not head_payload:
            return None

        return FactorSliceV1(
            history={"snapshots": snapshots},
            head=head_payload,
            meta=build_factor_meta(ctx=ctx, factor_name="sr"),
        )


FactorBundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]


def build_bundle() -> FactorBundleBuilders:
    return SrProcessor, SrSlicePlugin
