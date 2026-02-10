from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .anchor_semantics import build_anchor_history_from_switches, normalize_anchor_ref
from .factor_plugin_contract import FactorPluginSpec
from .factor_slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec
from .factor_slices import build_pen_head_preview
from .schemas import FactorMetaV1, FactorSliceV1
from .zhongshu import build_alive_zhongshu_from_confirmed_pens

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

_PEN_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="pen",
        event_kind="pen.confirmed",
        bucket_name="pen_confirmed",
        sort_keys=("visible_time", "start_time"),
    ),
)

_ZHONGSHU_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="zhongshu",
        event_kind="zhongshu.dead",
        bucket_name="zhongshu_dead",
    ),
)

_ANCHOR_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (
    SliceBucketSpec(
        factor_name="anchor",
        event_kind="anchor.switch",
        bucket_name="anchor_switches",
        sort_keys=("visible_time", "switch_time"),
    ),
)


def _meta(*, ctx: FactorSliceBuildContext, factor_name: str) -> FactorMetaV1:
    return FactorMetaV1(
        series_id=ctx.series_id,
        at_time=int(ctx.aligned_time),
        candle_id=ctx.candle_id,
        factor_name=factor_name,
    )


def _anchor_ref_strength(*, ref: dict[str, int | str] | None, pen_confirmed: list[dict[str, Any]]) -> float:
    if not isinstance(ref, dict):
        return -1.0
    st = int(ref.get("start_time") or 0)
    direction = int(ref.get("direction") or 0)
    if st <= 0 or direction not in {-1, 1}:
        return -1.0
    best = None
    for pen in pen_confirmed:
        if int(pen.get("start_time") or 0) == st and int(pen.get("direction") or 0) == direction:
            if best is None or int(best.get("end_time") or 0) <= int(pen.get("end_time") or 0):
                best = pen
    if best is None:
        return -1.0
    return abs(float(best.get("end_price") or 0.0) - float(best.get("start_price") or 0.0))


def _candidate_anchor_from_pen_head(pen_head_candidate: Any) -> tuple[dict[str, int | str] | None, float]:
    if not isinstance(pen_head_candidate, dict):
        return None, -1.0
    try:
        candidate_ref = normalize_anchor_ref(
            {
                "kind": "candidate",
                "start_time": int(pen_head_candidate.get("start_time") or 0),
                "end_time": int(pen_head_candidate.get("end_time") or 0),
                "direction": int(pen_head_candidate.get("direction") or 0),
            }
        )
        candidate_strength = abs(
            float(pen_head_candidate.get("end_price") or 0.0) - float(pen_head_candidate.get("start_price") or 0.0)
        )
    except Exception:
        return None, -1.0
    return candidate_ref, float(candidate_strength)


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
            meta=_meta(ctx=ctx, factor_name="pivot"),
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
                candles = ctx.candle_store.get_closed(
                    ctx.series_id,
                    since=int(ctx.start_time),
                    limit=int(ctx.window_candles) + 5,
                )
                candles = [c for c in candles if int(c.candle_time) <= int(ctx.aligned_time)]
            except Exception:
                candles = []

            preview = build_pen_head_preview(
                candles=candles,
                major_pivots=list(ctx.buckets.get("piv_major") or []),
                aligned_time=int(ctx.aligned_time),
            )
            for key in ("extending", "candidate"):
                value = preview.get(key)
                if isinstance(value, dict):
                    pen_head[key] = value

        return FactorSliceV1(
            history={"confirmed": pen_confirmed},
            head=pen_head,
            meta=_meta(ctx=ctx, factor_name="pen"),
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
            zhongshu_head["alive"] = []
            try:
                candles_for_zs = ctx.candle_store.get_closed_between_times(
                    ctx.series_id,
                    start_time=int(ctx.start_time),
                    end_time=int(ctx.aligned_time),
                    limit=int(ctx.window_candles) + 10,
                )
                alive = build_alive_zhongshu_from_confirmed_pens(
                    pen_confirmed,
                    up_to_visible_time=int(ctx.aligned_time),
                    candles=candles_for_zs,
                )
            except Exception:
                alive = None

            if alive is not None and int(alive.visible_time) == int(ctx.aligned_time):
                zhongshu_head["alive"] = [
                    {
                        "start_time": int(alive.start_time),
                        "end_time": int(alive.end_time),
                        "zg": float(alive.zg),
                        "zd": float(alive.zd),
                        "entry_direction": int(alive.entry_direction),
                        "formed_time": int(alive.formed_time),
                        "formed_reason": str(alive.formed_reason),
                        "death_time": None,
                        "visible_time": int(alive.visible_time),
                    }
                ]
        elif zhongshu_head_row is not None and int(zhongshu_head_row.candle_time) == int(ctx.aligned_time):
            head = dict(zhongshu_head_row.head or {})
            alive = head.get("alive")
            if isinstance(alive, list):
                zhongshu_head["alive"] = alive

        if not zhongshu_dead and not zhongshu_head.get("alive"):
            return None

        return FactorSliceV1(
            history={"dead": zhongshu_dead},
            head=zhongshu_head,
            meta=_meta(ctx=ctx, factor_name="zhongshu"),
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
        pen_head_candidate = None
        pen_slice = ctx.snapshots.get("pen")
        if pen_slice is not None:
            pen_head_candidate = (pen_slice.head or {}).get("candidate")

        anchor_head_row = ctx.head_rows.get("anchor")
        if anchor_head_row is not None:
            anchor_head = dict(anchor_head_row.head or {})
            current_anchor_ref = normalize_anchor_ref(anchor_head.get("current_anchor_ref"))
        else:
            current_anchor_ref = None
            if history_switches:
                cur = history_switches[-1].get("new_anchor")
                if isinstance(cur, dict):
                    current_anchor_ref = normalize_anchor_ref(cur)
            elif pen_confirmed:
                last = pen_confirmed[-1]
                current_anchor_ref = {
                    "kind": "confirmed",
                    "start_time": int(last.get("start_time") or 0),
                    "end_time": int(last.get("end_time") or 0),
                    "direction": int(last.get("direction") or 0),
                }

        candidate_ref, candidate_strength = _candidate_anchor_from_pen_head(pen_head_candidate)
        current_strength = _anchor_ref_strength(ref=current_anchor_ref, pen_confirmed=pen_confirmed)
        if candidate_ref is not None:
            current_start = int(current_anchor_ref.get("start_time") or 0) if isinstance(current_anchor_ref, dict) else 0
            candidate_start = int(candidate_ref.get("start_time") or 0)
            if current_anchor_ref is None or candidate_start == current_start or candidate_strength > current_strength:
                current_anchor_ref = dict(candidate_ref)

        return FactorSliceV1(
            history={"anchors": history_anchors, "switches": history_switches},
            head={"current_anchor_ref": current_anchor_ref},
            meta=_meta(ctx=ctx, factor_name="anchor"),
        )


def build_default_factor_slice_plugins() -> tuple[FactorSlicePlugin, ...]:
    return (
        PivotSlicePlugin(),
        PenSlicePlugin(),
        ZhongshuSlicePlugin(),
        AnchorSlicePlugin(),
    )
