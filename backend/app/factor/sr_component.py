from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .sr_analyzer import SrAnalyzerParams, SrPriceLevel, SupportResistanceAnalyzer


class SrCandleLike(Protocol):
    candle_time: int
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SrParams:
    tolerance_atr: float = 0.5
    cross_atr_multiplier: float = 0.5
    min_touches: int = 2
    max_levels: int = 10
    flip_pivot_count: int = 3
    broken_cross_count: int = 3
    atr_period: int = 14
    cluster_pivot_limit: int | None = 200


def build_sr_snapshot(
    *,
    candles: list[SrCandleLike],
    major_pivots: list[dict[str, Any]],
    time_to_idx: dict[int, int],
    params: SrParams,
) -> dict[str, Any]:
    if len(candles) < 5:
        return {"algorithm": "", "levels": [], "pivots": []}
    pivot_data = _build_pivot_data(
        major_pivots=major_pivots,
        max_idx=len(candles) - 1,
        time_to_idx=time_to_idx,
    )
    if not pivot_data["resistance_pivots"] and not pivot_data["support_pivots"]:
        return {"algorithm": "", "levels": [], "pivots": []}

    analyzer = SupportResistanceAnalyzer(
        params=SrAnalyzerParams(
            tolerance_atr=float(params.tolerance_atr),
            cross_atr_multiplier=float(params.cross_atr_multiplier),
            min_touches=int(params.min_touches),
            max_levels=int(params.max_levels),
            flip_pivot_count=int(params.flip_pivot_count),
            broken_cross_count=int(params.broken_cross_count),
            atr_period=int(params.atr_period),
            cluster_pivot_limit=params.cluster_pivot_limit,
        )
    )
    levels = analyzer.find_levels(candles=candles, pivot_data=pivot_data)
    if not levels:
        return {"algorithm": "", "levels": [], "pivots": []}

    normalized_levels, pivots = _convert_levels(candles=candles, levels=levels)
    return {
        "algorithm": "pivot_wick_overlap",
        "levels": normalized_levels,
        "pivots": pivots,
    }


def _build_pivot_data(
    *,
    major_pivots: list[dict[str, Any]],
    max_idx: int,
    time_to_idx: dict[int, int],
) -> dict[str, list[dict[str, Any]]]:
    resistance_pivots: list[dict[str, Any]] = []
    support_pivots: list[dict[str, Any]] = []
    for pivot in major_pivots:
        direction = str(pivot.get("direction") or "")
        if direction not in {"resistance", "support"}:
            continue
        raw_idx = pivot.get("pivot_idx")
        pivot_idx = int(raw_idx) if raw_idx is not None else int(time_to_idx.get(int(pivot.get("pivot_time") or 0), -1))
        if pivot_idx < 0 or pivot_idx > int(max_idx):
            continue
        price = float(pivot.get("pivot_price") or 0.0)
        if price <= 0:
            continue
        item = {
            "idx": int(pivot_idx),
            "price": float(price),
            "source_window": "major",
        }
        if direction == "resistance":
            resistance_pivots.append(item)
        else:
            support_pivots.append(item)
    return {
        "resistance_pivots": resistance_pivots,
        "support_pivots": support_pivots,
    }


def _convert_levels(*, candles: list[SrCandleLike], levels: list[SrPriceLevel]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output_levels: list[dict[str, Any]] = []
    output_pivots: list[dict[str, Any]] = []
    for level in levels:
        level_type = "resistance" if level.level_type == "res" else "support"
        render_type = "flip" if level.status == "flip" else level_type
        second_idx = int(level.touch_indices[1]) if len(level.touch_indices) > 1 else None
        touch_times = [
            int(candles[idx].candle_time)
            for idx in level.touch_indices
            if 0 <= int(idx) < len(candles)
        ]
        output_levels.append(
            {
                "price": float(level.price),
                "type": render_type,
                "level_type": level_type,
                "status": str(level.status),
                "first_idx": int(level.first_touch_idx),
                "second_idx": int(second_idx) if second_idx is not None else None,
                "last_idx": int(level.last_touch_idx),
                "first_time": int(candles[level.first_touch_idx].candle_time) if 0 <= level.first_touch_idx < len(candles) else None,
                "second_time": int(candles[second_idx].candle_time)
                if second_idx is not None and 0 <= int(second_idx) < len(candles)
                else None,
                "last_time": int(candles[level.last_touch_idx].candle_time) if 0 <= level.last_touch_idx < len(candles) else None,
                "count": int(level.touches),
                "flip_dir": level.flip_dir,
                "touch_indices": [int(idx) for idx in level.touch_indices],
                "touch_times": touch_times,
                "level_score": float(level.level_score),
                "band_low": float(level.band_low) if level.band_low is not None else None,
                "band_high": float(level.band_high) if level.band_high is not None else None,
                "band_width_atr": float(level.band_width_atr) if level.band_width_atr is not None else None,
                "death_idx": int(level.death_idx) if level.death_idx is not None else None,
                "death_time": int(level.death_time) if level.death_time is not None else None,
                "death_price": float(level.price) if level.death_time is not None else None,
            }
        )
        for idx in level.touch_indices:
            if idx < 0 or idx >= len(candles):
                continue
            output_pivots.append(
                {
                    "idx": int(idx),
                    "time": int(candles[idx].candle_time),
                    "price": float(level.price),
                    "type": render_type,
                    "source_window": "major",
                }
            )
    output_pivots.sort(key=lambda item: (int(item["idx"]), float(item["price"])))
    return output_levels, output_pivots
