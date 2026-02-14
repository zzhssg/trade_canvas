from __future__ import annotations

from collections.abc import Mapping


def calculate_atr(
    *,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> list[float]:
    count = min(len(highs), len(lows), len(closes))
    if count == 0:
        return []

    true_ranges: list[float] = []
    for idx in range(count):
        high = float(highs[idx])
        low = float(lows[idx])
        prev_close = float(closes[idx - 1]) if idx > 0 else float(closes[idx])
        true_range = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(float(max(0.0, true_range)))

    window = max(1, int(period))
    out: list[float] = []
    rolling_sum = 0.0
    for idx, true_range in enumerate(true_ranges):
        rolling_sum += float(true_range)
        if idx >= window:
            rolling_sum -= float(true_ranges[idx - window])
        divisor = min(idx + 1, window)
        out.append(float(rolling_sum / divisor))
    return out


def price_tolerance(
    *,
    atr_values: list[float],
    idx_a: int,
    idx_b: int,
    ref_price: float,
    tolerance_atr: float,
) -> float:
    atr_candidates: list[float] = []
    for idx in (int(idx_a), int(idx_b)):
        if idx < 0 or idx >= len(atr_values):
            continue
        value = float(atr_values[idx])
        if value > 0:
            atr_candidates.append(value)
    if atr_candidates:
        avg_atr = sum(atr_candidates) / len(atr_candidates)
        tol = float(avg_atr) * float(tolerance_atr)
        if tol > 0:
            return float(tol)
    base = float(ref_price) if float(ref_price) > 0 else 1.0
    return float(base * 0.002)


def count_cross_between(
    *,
    closes: list[float],
    idx_start: int,
    idx_end: int,
    line_price: float,
    tolerance: float,
) -> int:
    if not closes:
        return 0
    start = min(int(idx_start), int(idx_end)) + 1
    end = min(max(int(idx_start), int(idx_end)), len(closes) - 1)
    if end <= start:
        return 0

    transitions = 0
    prev_position = 0
    for idx in range(start, end):
        close_price = float(closes[idx])
        if close_price > float(line_price) + float(tolerance):
            position = 1
        elif close_price < float(line_price) - float(tolerance):
            position = -1
        else:
            position = 0
        if position == 0:
            continue
        if prev_position != 0 and position != prev_position:
            transitions += 1
        prev_position = position
    return int(transitions)


def clamp_band(
    *,
    overlap_low: float,
    overlap_high: float,
    atr_values: list[float],
    idx_a: int,
    idx_b: int,
    line_price: float,
) -> tuple[float, float, float]:
    low = min(float(overlap_low), float(overlap_high))
    high = max(float(overlap_low), float(overlap_high))
    width = max(0.0, high - low)

    atr_candidates: list[float] = []
    for idx in (int(idx_a), int(idx_b)):
        if idx < 0 or idx >= len(atr_values):
            continue
        value = float(atr_values[idx])
        if value > 0:
            atr_candidates.append(value)
    reference_atr = sum(atr_candidates) / len(atr_candidates) if atr_candidates else float(line_price) * 0.02
    if reference_atr <= 0:
        reference_atr = max(abs(float(line_price)) * 0.02, 1e-9)

    min_width = reference_atr * 0.5
    max_width = reference_atr * 3.0
    if width <= 0:
        width = min_width
    width = min(max(width, min_width), max_width)

    mid = (low + high) / 2.0
    band_low = mid - width / 2.0
    band_high = mid + width / 2.0
    return float(band_low), float(band_high), float(width / reference_atr)


def count_touches(
    *,
    pivots: list[Mapping[str, float | int | bool]],
    band_low: float,
    band_high: float,
    atr_values: list[float],
    tolerance_atr: float,
) -> tuple[int, int]:
    touches = 0
    major_touches = 0
    ref_price = (float(band_low) + float(band_high)) / 2.0
    for pivot in pivots:
        idx = int(pivot.get("idx", -1))
        if idx < 0:
            continue
        tolerance = price_tolerance(
            atr_values=atr_values,
            idx_a=idx,
            idx_b=idx,
            ref_price=ref_price,
            tolerance_atr=tolerance_atr,
        )
        wick_low = float(pivot.get("wick_low", 0.0))
        wick_high = float(pivot.get("wick_high", 0.0))
        if wick_high < float(band_low) - tolerance:
            continue
        if wick_low > float(band_high) + tolerance:
            continue
        touches += 1
        if bool(pivot.get("is_major", False)):
            major_touches += 1
    return int(touches), int(major_touches)


def detect_status(
    *,
    line_price: float,
    current_price: float,
    start_idx: int,
    atr_values: list[float],
    closes: list[float],
    tolerance_atr: float,
    broken_cross_count: int,
) -> tuple[str, str | None, int | None]:
    if not closes:
        return "active", None, None
    current_atr = float(atr_values[-1]) if atr_values else float(line_price) * 0.02
    if current_atr <= 0:
        current_atr = max(abs(float(line_price)) * 0.02, 1e-9)
    tolerance = float(current_atr) * float(tolerance_atr)

    start = max(0, int(start_idx) + 1)
    if start >= len(closes):
        return "active", None, None

    transitions = 0
    last_transition_idx: int | None = None
    prev_position = 0
    for idx in range(start, len(closes)):
        close_price = float(closes[idx])
        if close_price > float(line_price) + tolerance:
            position = 1
        elif close_price < float(line_price) - tolerance:
            position = -1
        else:
            position = 0
        if position == 0:
            continue
        if prev_position != 0 and position != prev_position:
            transitions += 1
            last_transition_idx = int(idx)
            if transitions >= int(broken_cross_count):
                return "broken", None, int(idx)
        prev_position = position

    if transitions == 0:
        return "active", None, None
    if float(current_price) > float(line_price) + tolerance:
        return "flip", "up", last_transition_idx
    if float(current_price) < float(line_price) - tolerance:
        return "flip", "down", last_transition_idx
    return "flip", None, last_transition_idx
