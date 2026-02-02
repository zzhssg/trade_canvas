from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .schemas import CandleClosed


@dataclass(frozen=True, slots=True)
class PivotPointV0:
    pivot_time: int
    pivot_idx: int
    pivot_price: float
    direction: str  # "resistance" | "support"
    visible_time: int
    visible_idx: int
    window: int


def compute_major_pivots(candles: list[CandleClosed], *, window: int) -> list[PivotPointV0]:
    """
    Major pivot (time_major) confirmation (trade_system semantics):
    - Confirm pivot at pivot_idx when we have left/right `window` candles.
    - visible_idx = pivot_idx + window (delay).
    - Plateau de-dupe: left side strict, right side allows equality (keep the earliest pivot on a plateau).
    """
    w = int(window)
    if w <= 0:
        return []

    n = len(candles)
    if n < 2 * w + 1:
        return []

    out: list[PivotPointV0] = []
    for pivot_idx in range(w, n - w):
        visible_idx = pivot_idx + w
        start = pivot_idx - w
        end = pivot_idx + w

        # Local max (resistance)
        target_high = float(candles[pivot_idx].high)
        is_max_left = True
        for i in range(start, pivot_idx):
            if float(candles[i].high) >= target_high:
                is_max_left = False
                break
        if is_max_left:
            is_max_right = True
            for i in range(pivot_idx + 1, end + 1):
                if float(candles[i].high) > target_high:
                    is_max_right = False
                    break
            if is_max_right:
                out.append(
                    PivotPointV0(
                        pivot_time=int(candles[pivot_idx].candle_time),
                        pivot_idx=int(pivot_idx),
                        pivot_price=float(target_high),
                        direction="resistance",
                        visible_time=int(candles[visible_idx].candle_time),
                        visible_idx=int(visible_idx),
                        window=int(w),
                    )
                )

        # Local min (support)
        target_low = float(candles[pivot_idx].low)
        is_min_left = True
        for i in range(start, pivot_idx):
            if float(candles[i].low) <= target_low:
                is_min_left = False
                break
        if is_min_left:
            is_min_right = True
            for i in range(pivot_idx + 1, end + 1):
                if float(candles[i].low) < target_low:
                    is_min_right = False
                    break
            if is_min_right:
                out.append(
                    PivotPointV0(
                        pivot_time=int(candles[pivot_idx].candle_time),
                        pivot_idx=int(pivot_idx),
                        pivot_price=float(target_low),
                        direction="support",
                        visible_time=int(candles[visible_idx].candle_time),
                        visible_idx=int(visible_idx),
                        window=int(w),
                    )
                )

    return out


def compute_minor_pivots(candles: list[CandleClosed], *, window: int) -> list[PivotPointV0]:
    """
    Minor pivot confirmation (trade_system IncrementalMinorPivotDetector semantics, but v0 uses segment_start=0):
    - At visible_idx=i, confirm center_idx=i-window using window [i-2w, i] (length 2w+1).
    - If center high >= max(high) in window -> resistance.
    - If center low <= min(low) in window -> support.
    """
    w = int(window)
    if w <= 0:
        return []

    n = len(candles)
    if n < 2 * w + 1:
        return []

    max_dq: deque[tuple[int, float]] = deque()
    min_dq: deque[tuple[int, float]] = deque()

    def prune(i: int) -> None:
        window_len = 2 * w
        while max_dq and max_dq[0][0] < i - window_len:
            max_dq.popleft()
        while min_dq and min_dq[0][0] < i - window_len:
            min_dq.popleft()

    def push(i: int, high: float, low: float) -> None:
        while max_dq and max_dq[-1][1] <= float(high):
            max_dq.pop()
        max_dq.append((int(i), float(high)))
        while min_dq and min_dq[-1][1] >= float(low):
            min_dq.pop()
        min_dq.append((int(i), float(low)))
        prune(i)

    out: list[PivotPointV0] = []
    for i in range(n):
        push(i, float(candles[i].high), float(candles[i].low))

        if i < 2 * w:
            continue
        center_idx = i - w
        if center_idx < w:
            continue

        max_val = max_dq[0][1] if max_dq else None
        min_val = min_dq[0][1] if min_dq else None
        if max_val is None or min_val is None:
            continue

        center_high = float(candles[center_idx].high)
        if center_high >= float(max_val):
            out.append(
                PivotPointV0(
                    pivot_time=int(candles[center_idx].candle_time),
                    pivot_idx=int(center_idx),
                    pivot_price=float(center_high),
                    direction="resistance",
                    visible_time=int(candles[i].candle_time),
                    visible_idx=int(i),
                    window=int(w),
                )
            )

        center_low = float(candles[center_idx].low)
        if center_low <= float(min_val):
            out.append(
                PivotPointV0(
                    pivot_time=int(candles[center_idx].candle_time),
                    pivot_idx=int(center_idx),
                    pivot_price=float(center_low),
                    direction="support",
                    visible_time=int(candles[i].candle_time),
                    visible_idx=int(i),
                    window=int(w),
                )
            )

    return out


def compute_minor_pivots_segment(
    candles: list[CandleClosed],
    *,
    segment_start_idx: int,
    window: int,
    end_idx: int | None = None,
) -> list[PivotPointV0]:
    """
    Minor pivot confirmation with a segment boundary (trade_system semantics):
    - segment_start_idx is usually last_major_pivot_idx.
    - Only confirm pivots whose left/right window are fully within the segment.
    """
    w = int(window)
    if w <= 0:
        return []

    n = len(candles)
    if n <= 0:
        return []

    seg_start = int(segment_start_idx)
    if seg_start < 0:
        return []

    if end_idx is None:
        end_i = n - 1
    else:
        end_i = min(n - 1, int(end_idx))

    if end_i - seg_start + 1 < 2 * w + 1:
        return []

    max_dq: deque[tuple[int, float]] = deque()
    min_dq: deque[tuple[int, float]] = deque()

    def prune(i: int) -> None:
        window_len = 2 * w
        while max_dq and max_dq[0][0] < i - window_len:
            max_dq.popleft()
        while min_dq and min_dq[0][0] < i - window_len:
            min_dq.popleft()

    def push(i: int, high: float, low: float) -> None:
        while max_dq and max_dq[-1][1] <= float(high):
            max_dq.pop()
        max_dq.append((int(i), float(high)))
        while min_dq and min_dq[-1][1] >= float(low):
            min_dq.pop()
        min_dq.append((int(i), float(low)))
        prune(i)

    out: list[PivotPointV0] = []
    for i in range(seg_start, end_i + 1):
        push(i, float(candles[i].high), float(candles[i].low))

        # Need full 2w+1 coverage within segment.
        if i - 2 * w < seg_start:
            continue
        center_idx = i - w
        if center_idx - seg_start < w:
            continue

        max_val = max_dq[0][1] if max_dq else None
        min_val = min_dq[0][1] if min_dq else None
        if max_val is None or min_val is None:
            continue

        center_high = float(candles[center_idx].high)
        if center_high >= float(max_val):
            out.append(
                PivotPointV0(
                    pivot_time=int(candles[center_idx].candle_time),
                    pivot_idx=int(center_idx),
                    pivot_price=float(center_high),
                    direction="resistance",
                    visible_time=int(candles[i].candle_time),
                    visible_idx=int(i),
                    window=int(w),
                )
            )

        center_low = float(candles[center_idx].low)
        if center_low <= float(min_val):
            out.append(
                PivotPointV0(
                    pivot_time=int(candles[center_idx].candle_time),
                    pivot_idx=int(center_idx),
                    pivot_price=float(center_low),
                    direction="support",
                    visible_time=int(candles[i].candle_time),
                    visible_idx=int(i),
                    window=int(w),
                )
            )

    return out
