from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from ..head_builder import build_zhongshu_alive_head
from ..plugin_contract import FactorPluginSpec
from ..processor_zhongshu import ZhongshuProcessor
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from ...core.schemas import FactorSliceV1
from .common import build_factor_meta

_ZHONGSHU_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="zhongshu",
        event_kind="zhongshu.dead",
        bucket_name="zhongshu_dead",
    ),
)


@dataclass(frozen=True)
class ZhongshuSlicePlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="zhongshu", depends_on=("pen",))
    bucket_specs: tuple[SliceBucketSpec, ...] = _ZHONGSHU_BUCKET_SPECS

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:
        pen_confirmed = list(ctx.buckets.get("pen_confirmed") or [])
        zhongshu_dead = list(ctx.buckets.get("zhongshu_dead") or [])
        zhongshu_head_row = ctx.head_rows.get("zhongshu")

        zhongshu_head: dict[str, Any] = {}
        if pen_confirmed:
            try:
                candles_for_zhongshu = ctx.candle_store.get_closed_between_times(
                    ctx.series_id,
                    start_time=int(ctx.start_time),
                    end_time=int(ctx.aligned_time),
                    limit=int(ctx.window_candles) + 10,
                )
                zhongshu_head = build_zhongshu_alive_head(
                    zhongshu_state={},
                    confirmed_pens=pen_confirmed,
                    candles=candles_for_zhongshu,
                    aligned_time=int(ctx.aligned_time),
                )
            except Exception:
                zhongshu_head = {"alive": []}
        elif zhongshu_head_row is not None and int(zhongshu_head_row.candle_time) == int(ctx.aligned_time):
            zhongshu_head = build_zhongshu_alive_head(
                zhongshu_state=dict(zhongshu_head_row.head or {}),
                confirmed_pens=[],
                candles=[],
                aligned_time=int(ctx.aligned_time),
            )

        if not zhongshu_dead and not zhongshu_head.get("alive"):
            return None

        return FactorSliceV1(
            history={"dead": zhongshu_dead},
            head=zhongshu_head,
            meta=build_factor_meta(ctx=ctx, factor_name="zhongshu"),
        )


FactorBundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]


def build_bundle() -> FactorBundleBuilders:
    return ZhongshuProcessor, ZhongshuSlicePlugin
