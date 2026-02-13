from __future__ import annotations

from typing import Any

from ..anchor_semantics import normalize_anchor_ref
from ..slice_plugin_contract import FactorSliceBuildContext
from ...core.schemas import FactorMetaV1


def build_factor_meta(*, ctx: FactorSliceBuildContext, factor_name: str) -> FactorMetaV1:
    return FactorMetaV1(
        series_id=ctx.series_id,
        at_time=int(ctx.aligned_time),
        candle_id=ctx.candle_id,
        factor_name=factor_name,
    )


def anchor_ref_strength(*, ref: dict[str, int | str] | None, pen_confirmed: list[dict[str, Any]]) -> float:
    if not isinstance(ref, dict):
        return -1.0
    start_time = int(ref.get("start_time") or 0)
    direction = int(ref.get("direction") or 0)
    if start_time <= 0 or direction not in {-1, 1}:
        return -1.0

    best: dict[str, Any] | None = None
    for pen in pen_confirmed:
        if int(pen.get("start_time") or 0) != start_time:
            continue
        if int(pen.get("direction") or 0) != direction:
            continue
        if best is None or int(best.get("end_time") or 0) <= int(pen.get("end_time") or 0):
            best = pen

    if best is None:
        return -1.0

    return abs(float(best.get("end_price") or 0.0) - float(best.get("start_price") or 0.0))


def candidate_anchor_from_pen_head(
    pen_head_candidate: Any,
) -> tuple[dict[str, int | str] | None, float]:
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
            float(pen_head_candidate.get("end_price") or 0.0)
            - float(pen_head_candidate.get("start_price") or 0.0)
        )
    except (ValueError, TypeError):
        return None, -1.0

    return candidate_ref, float(candidate_strength)
