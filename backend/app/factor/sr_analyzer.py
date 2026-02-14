from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from .sr_analyzer_support import (
    calculate_atr,
    clamp_band,
    count_cross_between,
    count_touches,
    detect_status,
    price_tolerance,
)

class SrCandleLike(Protocol):
    candle_time: int
    high: float
    low: float
    close: float

@dataclass(frozen=True)
class SrPriceLevel:
    price: float
    level_type: str = "res"
    touches: int = 0
    first_touch_idx: int = 0
    last_touch_idx: int = 0
    status: str = "active"
    flip_dir: str | None = None
    touch_indices: tuple[int, ...] = field(default_factory=tuple)
    distance_to_current: float = 0.0
    death_idx: int | None = None
    death_time: int | None = None
    level_score: float = 0.0
    band_low: float | None = None
    band_high: float | None = None
    band_width_atr: float | None = None
@dataclass(frozen=True)
class SrAnalyzerParams:
    tolerance_atr: float = 0.5
    cross_atr_multiplier: float = 0.5
    min_touches: int = 2
    max_levels: int = 10
    flip_pivot_count: int = 3
    broken_cross_count: int = 3
    atr_period: int = 14
    cluster_pivot_limit: int | None = 200
@dataclass(frozen=True)
class _LevelBuildContext:
    candles: list[SrCandleLike]
    pivots: list[Mapping[str, float | int | bool]]
    start: Mapping[str, float | int | bool]
    chosen: Mapping[str, float | int | bool]
    kind: str
    line_price: float
    overlap_low: float
    overlap_high: float
    atr_values: list[float]
    closes: list[float]
    current_price: float
class SupportResistanceAnalyzer:
    def __init__(self, *, params: SrAnalyzerParams) -> None:
        self._params = params

    def find_levels(self, *, candles: list[SrCandleLike], pivot_data: dict[str, list[dict]] | None) -> list[SrPriceLevel]:
        if len(candles) < 5 or not pivot_data:
            return []

        highs = [float(candle.high) for candle in candles]
        lows = [float(candle.low) for candle in candles]
        closes = [float(candle.close) for candle in candles]
        atr_values = calculate_atr(highs=highs, lows=lows, closes=closes, period=int(self._params.atr_period))
        current_price = float(closes[-1])

        resistance_pivots = self._normalize_pivots(
            pivots=list(pivot_data.get("resistance_pivots") or []),
            candles=candles,
        )
        support_pivots = self._normalize_pivots(
            pivots=list(pivot_data.get("support_pivots") or []),
            candles=candles,
        )
        if self._params.cluster_pivot_limit is not None and self._params.cluster_pivot_limit > 0:
            limit = int(self._params.cluster_pivot_limit)
            resistance_pivots = sorted(resistance_pivots, key=lambda item: int(item["idx"]))[-limit:]
            support_pivots = sorted(support_pivots, key=lambda item: int(item["idx"]))[-limit:]

        levels: list[SrPriceLevel] = []
        levels.extend(
            self._build_levels(
                candles=candles,
                pivots=resistance_pivots,
                kind="res",
                atr_values=atr_values,
                closes=closes,
                current_price=current_price,
            )
        )
        levels.extend(
            self._build_levels(
                candles=candles,
                pivots=support_pivots,
                kind="sup",
                atr_values=atr_values,
                closes=closes,
                current_price=current_price,
            )
        )

        levels.sort(key=lambda item: float(item.distance_to_current))
        active = [item for item in levels if str(item.status) in {"active", "flip"}]
        broken = [item for item in levels if str(item.status) not in {"active", "flip"}]
        return list(active[: int(self._params.max_levels)]) + sorted(broken, key=lambda item: float(item.distance_to_current))

    def _normalize_pivots(self, *, pivots: list[dict], candles: list[SrCandleLike]) -> list[Mapping[str, float | int | bool]]:
        out: list[Mapping[str, float | int | bool]] = []
        for pivot in pivots:
            try:
                idx = int(pivot.get("idx", -1))
                price = float(pivot.get("price", 0.0))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(candles):
                continue
            if price <= 0:
                continue
            candle = candles[idx]
            source_window = str(pivot.get("source_window") or "major")
            out.append(
                {
                    "idx": int(idx),
                    "price": float(price),
                    "is_major": bool(source_window in {"major", "both"}),
                    "wick_high": float(candle.high),
                    "wick_low": float(candle.low),
                }
            )
        return out

    def _build_levels(
        self,
        *,
        candles: list[SrCandleLike],
        pivots: list[Mapping[str, float | int | bool]],
        kind: str,
        atr_values: list[float],
        closes: list[float],
        current_price: float,
    ) -> list[SrPriceLevel]:
        majors = [item for item in pivots if bool(item["is_major"])]
        if len(majors) < 2:
            return []

        out: list[SrPriceLevel] = []
        for start in sorted(majors, key=lambda item: int(item["idx"]), reverse=True):
            chosen, overlap_low, overlap_high, tolerance = self._pick_overlap(
                pivots=majors,
                start=start,
                kind=kind,
                atr_values=atr_values,
                closes=closes,
            )
            if chosen is None:
                continue
            line_price = float(overlap_high if kind == "res" else overlap_low)
            level = self._build_level(
                ctx=_LevelBuildContext(
                    candles=candles,
                    pivots=pivots,
                    start=start,
                    chosen=chosen,
                    kind=kind,
                    line_price=line_price,
                    overlap_low=float(overlap_low),
                    overlap_high=float(overlap_high),
                    atr_values=atr_values,
                    closes=closes,
                    current_price=float(current_price),
                )
            )
            self._upsert_level(levels=out, level=level, tolerance=float(tolerance), line_price=line_price)
        return out

    def _pick_overlap(
        self,
        *,
        pivots: list[Mapping[str, float | int | bool]],
        start: Mapping[str, float | int | bool],
        kind: str,
        atr_values: list[float],
        closes: list[float],
    ) -> tuple[Mapping[str, float | int | bool] | None, float, float, float]:
        for candidate in sorted(
            [item for item in pivots if int(item["idx"]) < int(start["idx"])],
            key=lambda item: int(item["idx"]),
            reverse=True,
        ):
            overlap_low = max(float(candidate["wick_low"]), float(start["wick_low"]))
            overlap_high = min(float(candidate["wick_high"]), float(start["wick_high"]))
            tolerance = price_tolerance(
                atr_values=atr_values,
                idx_a=int(start["idx"]),
                idx_b=int(candidate["idx"]),
                ref_price=float(overlap_high if kind == "res" else overlap_low),
                tolerance_atr=float(self._params.tolerance_atr),
            )
            if overlap_low > overlap_high + tolerance:
                continue
            line_price = overlap_high if kind == "res" else overlap_low
            crosses = count_cross_between(
                closes=closes,
                idx_start=int(candidate["idx"]),
                idx_end=int(start["idx"]),
                line_price=float(line_price),
                tolerance=float(tolerance),
            )
            if crosses > int(self._params.broken_cross_count):
                continue
            return candidate, float(overlap_low), float(overlap_high), float(tolerance)
        return None, 0.0, 0.0, 0.0

    def _build_level(self, *, ctx: _LevelBuildContext) -> SrPriceLevel:
        candles = ctx.candles
        pivots = ctx.pivots
        start = ctx.start
        chosen = ctx.chosen
        kind = str(ctx.kind)
        line_price = float(ctx.line_price)
        overlap_low = float(ctx.overlap_low)
        overlap_high = float(ctx.overlap_high)
        atr_values = ctx.atr_values
        closes = ctx.closes
        current_price = float(ctx.current_price)
        band_low, band_high, band_width_atr = clamp_band(
            overlap_low=float(overlap_low),
            overlap_high=float(overlap_high),
            atr_values=atr_values,
            idx_a=int(chosen["idx"]),
            idx_b=int(start["idx"]),
            line_price=float(line_price),
        )
        touches, major_touches = count_touches(
            pivots=pivots,
            band_low=float(band_low),
            band_high=float(band_high),
            atr_values=atr_values,
            tolerance_atr=float(self._params.tolerance_atr),
        )
        touches_score = min(1.0, float(touches) / 4.0) if touches > 0 else 0.0
        level_weight = float(major_touches) / float(touches) if touches > 0 else 0.0
        level_score = 0.5 * touches_score + 0.5 * level_weight

        touch_indices = sorted((int(chosen["idx"]), int(start["idx"])))
        status, flip_dir, death_idx = detect_status(
            line_price=float(line_price),
            current_price=float(current_price),
            start_idx=int(touch_indices[-1]),
            atr_values=atr_values,
            closes=closes,
            tolerance_atr=float(self._params.tolerance_atr),
            broken_cross_count=int(self._params.broken_cross_count),
        )
        death_time = int(candles[death_idx].candle_time) if death_idx is not None and 0 <= death_idx < len(candles) else None
        return SrPriceLevel(
            price=float(line_price),
            level_type=str(kind),
            touches=int(max(int(self._params.min_touches), touches)),
            first_touch_idx=int(touch_indices[0]),
            last_touch_idx=int(touch_indices[-1]),
            status=str(status),
            flip_dir=flip_dir,
            touch_indices=tuple(int(idx) for idx in touch_indices),
            distance_to_current=abs(float(line_price) - float(current_price)),
            death_idx=death_idx,
            death_time=death_time,
            level_score=float(level_score),
            band_low=float(band_low),
            band_high=float(band_high),
            band_width_atr=float(band_width_atr),
        )

    def _upsert_level(self, *, levels: list[SrPriceLevel], level: SrPriceLevel, tolerance: float, line_price: float) -> None:
        dedup_tolerance = max(abs(float(line_price)) * 0.001, float(tolerance) * 0.5)
        for idx, existing in enumerate(levels):
            if abs(float(existing.price) - float(line_price)) > dedup_tolerance:
                continue
            if existing.status == "broken" and level.status != "broken":
                levels[idx] = level
                return
            if level.status != "broken" and int(level.last_touch_idx) > int(existing.last_touch_idx):
                levels[idx] = level
                return
            return
        levels.append(level)
