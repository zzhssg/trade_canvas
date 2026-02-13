from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from ..head_builder import build_pen_head_snapshot
from ..plugin_contract import FactorPluginSpec
from ..processor_pen import PenProcessor
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from ...core.schemas import FactorSliceV1
from .common import build_factor_meta

_PEN_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="pen",
        event_kind="pen.confirmed",
        bucket_name="pen_confirmed",
        sort_keys=("visible_time", "start_time"),
    ),
)


@dataclass(frozen=True)
class PenSlicePlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="pen", depends_on=("pivot",))
    bucket_specs: tuple[SliceBucketSpec, ...] = _PEN_BUCKET_SPECS

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:
        pen_confirmed = list(ctx.buckets.get("pen_confirmed") or [])
        if not pen_confirmed:
            return None

        pen_head: dict[str, Any] = {}
        pen_head_row = ctx.head_rows.get("pen")
        if pen_head_row is not None:
            pen_head = dict(pen_head_row.head or {})
        else:
            try:
                candles = ctx.candle_store.get_closed_between_times(
                    ctx.series_id,
                    start_time=int(ctx.start_time),
                    end_time=int(ctx.aligned_time),
                    limit=int(ctx.window_candles) + 5,
                )
            except Exception:
                candles = []

            built = build_pen_head_snapshot(
                confirmed_pens=pen_confirmed,
                candles=candles,
                effective_pivots=list(ctx.buckets.get("piv_major") or []),
                aligned_time=int(ctx.aligned_time),
            )
            if isinstance(built, dict):
                pen_head = built

        return FactorSliceV1(
            history={"confirmed": pen_confirmed},
            head=pen_head,
            meta=build_factor_meta(ctx=ctx, factor_name="pen"),
        )


FactorBundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]


def build_bundle() -> FactorBundleBuilders:
    return PenProcessor, PenSlicePlugin
