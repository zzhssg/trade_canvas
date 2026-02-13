from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from ..plugin_contract import FactorPluginSpec
from ..processor_pivot import PivotProcessor
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from ...core.schemas import FactorSliceV1
from .common import build_factor_meta

_PIVOT_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="pivot",
        event_kind="pivot.major",
        bucket_name="piv_major",
        sort_keys=("visible_time", "pivot_time"),
    ),
    SliceBucketSpec(
        factor_name="pivot",
        event_kind="pivot.minor",
        bucket_name="piv_minor",
    ),
)


@dataclass(frozen=True)
class PivotSlicePlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="pivot", depends_on=())
    bucket_specs: tuple[SliceBucketSpec, ...] = _PIVOT_BUCKET_SPECS

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:
        piv_major = list(ctx.buckets.get("piv_major") or [])
        if not piv_major:
            return None
        piv_minor = list(ctx.buckets.get("piv_minor") or [])
        return FactorSliceV1(
            history={"major": piv_major, "minor": piv_minor},
            head={},
            meta=build_factor_meta(ctx=ctx, factor_name="pivot"),
        )


FactorBundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]


def build_bundle() -> FactorBundleBuilders:
    return PivotProcessor, PivotSlicePlugin
