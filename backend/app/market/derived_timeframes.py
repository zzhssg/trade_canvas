from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

from ..core.flags import resolve_env_bool, resolve_env_str
from ..core.schemas import CandleClosed
from ..core.series_id import SeriesId, parse_series_id
from ..core.timeframe import timeframe_to_seconds


DEFAULT_DERIVED_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "4h", "1d")


def normalize_derived_timeframes(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        tf = str(value).strip()
        if not tf or tf in seen:
            continue
        seen.add(tf)
        out.append(tf)
    return tuple(out)


def derived_enabled() -> bool:
    return resolve_env_bool("TRADE_CANVAS_ENABLE_DERIVED_TIMEFRAMES", fallback=False)


def derived_base_timeframe() -> str:
    tf = resolve_env_str("TRADE_CANVAS_DERIVED_BASE_TIMEFRAME", fallback="1m")
    return tf or "1m"


def derived_timeframes() -> tuple[str, ...]:
    raw = resolve_env_str("TRADE_CANVAS_DERIVED_TIMEFRAMES", fallback="")
    if not raw:
        # Keep aligned with frontend defaults (ChartPanel.tsx) minus base 1m.
        return DEFAULT_DERIVED_TIMEFRAMES
    parts = [p.strip() for p in raw.split(",")]
    return normalize_derived_timeframes(parts)


def is_derived_series_id_with_config(
    series_id: str,
    *,
    enabled: bool,
    base_timeframe: str,
    derived: tuple[str, ...],
) -> bool:
    if not bool(enabled):
        return False
    s = parse_series_id(series_id)
    base = str(base_timeframe).strip() or "1m"
    if s.timeframe == base:
        return False
    return s.timeframe in set(normalize_derived_timeframes(derived))


def to_base_series_id_with_base(series_id: str, *, base_timeframe: str) -> str:
    s = parse_series_id(series_id)
    base = str(base_timeframe).strip() or "1m"
    return SeriesId(exchange=s.exchange, market=s.market, symbol=s.symbol, timeframe=base).raw


def is_derived_series_id(series_id: str) -> bool:
    return is_derived_series_id_with_config(
        series_id,
        enabled=derived_enabled(),
        base_timeframe=derived_base_timeframe(),
        derived=derived_timeframes(),
    )


def to_base_series_id(series_id: str) -> str:
    return to_base_series_id_with_base(series_id, base_timeframe=derived_base_timeframe())


def to_derived_series_id(base_series_id: str, *, timeframe: str) -> str:
    s = parse_series_id(base_series_id)
    return SeriesId(exchange=s.exchange, market=s.market, symbol=s.symbol, timeframe=str(timeframe)).raw


@dataclass
class _DerivedBucket:
    bucket_open_time: int | None = None
    minutes: dict[int, CandleClosed] | None = None  # finalized 1m candles within bucket
    last_emitted_bucket_open_time: int | None = None
    last_forming_emit_at: float = 0.0
    last_forming_bucket_open_time: int | None = None


def _align_bucket_open(*, t: int, tf_s: int) -> int:
    return int(t // tf_s) * int(tf_s)


def _merge_candles_to_derived(*, bucket_open_time: int, minutes: list[CandleClosed]) -> CandleClosed:
    minutes_sorted = minutes[:]
    minutes_sorted.sort(key=lambda c: int(c.candle_time))
    first = minutes_sorted[0]
    last = minutes_sorted[-1]
    return CandleClosed(
        candle_time=int(bucket_open_time),
        open=float(first.open),
        high=float(max(float(c.high) for c in minutes_sorted)),
        low=float(min(float(c.low) for c in minutes_sorted)),
        close=float(last.close),
        volume=float(sum(float(c.volume) for c in minutes_sorted)),
    )


class DerivedTimeframeFanout:
    """
    Fan out a 1m candle stream into multiple derived timeframes.

    - forming: best-effort, WS only, never persisted.
    - closed: emitted only when a bucket is complete (all minutes present), suitable for persistence.
    """

    def __init__(
        self,
        *,
        base_timeframe: str = "1m",
        derived: tuple[str, ...] = ("5m", "15m", "1h", "4h", "1d"),
        forming_min_interval_ms: int = 250,
    ) -> None:
        self._base_tf = str(base_timeframe).strip() or "1m"
        self._derived = tuple(str(x).strip() for x in derived if str(x).strip())
        self._forming_min_interval_s = max(0.0, float(int(forming_min_interval_ms)) / 1000.0)
        self._state: dict[tuple[str, str], _DerivedBucket] = {}

        self._base_s = timeframe_to_seconds(self._base_tf)
        if self._base_s <= 0:
            raise ValueError("invalid base timeframe")

        self._derived_tf_s: dict[str, int] = {}
        for tf in self._derived:
            tf_s = timeframe_to_seconds(tf)
            if tf_s <= 0:
                continue
            if tf_s % self._base_s != 0:
                # Skip non-multiples to avoid partial-minute drift.
                continue
            if tf_s == self._base_s:
                continue
            self._derived_tf_s[tf] = int(tf_s)

    @property
    def base_timeframe(self) -> str:
        return self._base_tf

    @property
    def derived_timeframes(self) -> tuple[str, ...]:
        return tuple(self._derived_tf_s.keys())

    def on_base_forming(
        self,
        *,
        base_series_id: str,
        candle: CandleClosed,
        now: float | None = None,
    ) -> list[tuple[str, CandleClosed]]:
        """
        Return derived forming candles (series_id, candle).
        """
        if not self._derived_tf_s:
            return []

        now_s = time.monotonic() if now is None else float(now)
        t = int(candle.candle_time)
        out: list[tuple[str, CandleClosed]] = []

        for tf, tf_s in self._derived_tf_s.items():
            key = (base_series_id, tf)
            st = self._state.get(key)
            if st is None:
                st = _DerivedBucket(bucket_open_time=None, minutes={})
                self._state[key] = st
            if st.minutes is None:
                st.minutes = {}

            bucket_open = _align_bucket_open(t=t, tf_s=tf_s)
            if st.bucket_open_time is None or int(st.bucket_open_time) != int(bucket_open):
                st.bucket_open_time = int(bucket_open)
                st.minutes.clear()

            # Throttle forming updates per derived series.
            if st.last_forming_bucket_open_time != int(bucket_open):
                st.last_forming_bucket_open_time = int(bucket_open)
                st.last_forming_emit_at = 0.0
            if self._forming_min_interval_s > 0 and (now_s - float(st.last_forming_emit_at or 0.0)) < self._forming_min_interval_s:
                continue

            finalized = list(st.minutes.values())
            merged = finalized + [candle]
            derived_candle = _merge_candles_to_derived(bucket_open_time=int(bucket_open), minutes=merged)

            out.append((to_derived_series_id(base_series_id, timeframe=tf), derived_candle))
            st.last_forming_emit_at = now_s

        return out

    def on_base_closed_batch(
        self,
        *,
        base_series_id: str,
        candles: list[CandleClosed],
    ) -> dict[str, list[CandleClosed]]:
        """
        Return derived closed candles to persist/publish, grouped by derived series_id.
        """
        if not candles or not self._derived_tf_s:
            return {}

        candles_sorted = candles[:]
        candles_sorted.sort(key=lambda c: int(c.candle_time))
        out: dict[str, list[CandleClosed]] = {}

        for tf, tf_s in self._derived_tf_s.items():
            key = (base_series_id, tf)
            st = self._state.get(key)
            if st is None:
                st = _DerivedBucket(bucket_open_time=None, minutes={})
                self._state[key] = st
            if st.minutes is None:
                st.minutes = {}

            bucket_size = int(tf_s // self._base_s)

            for c in candles_sorted:
                t = int(c.candle_time)
                bucket_open = _align_bucket_open(t=t, tf_s=tf_s)

                if st.bucket_open_time is None or int(st.bucket_open_time) != int(bucket_open):
                    st.bucket_open_time = int(bucket_open)
                    st.minutes.clear()

                st.minutes[t] = c

                expected_times = [int(bucket_open) + i * int(self._base_s) for i in range(bucket_size)]
                if not all(et in st.minutes for et in expected_times):
                    continue

                if st.last_emitted_bucket_open_time is not None and int(bucket_open) <= int(st.last_emitted_bucket_open_time):
                    continue

                derived_minutes = [st.minutes[et] for et in expected_times]
                derived_candle = _merge_candles_to_derived(bucket_open_time=int(bucket_open), minutes=derived_minutes)

                derived_series_id = to_derived_series_id(base_series_id, timeframe=tf)
                out.setdefault(derived_series_id, []).append(derived_candle)

                st.last_emitted_bucket_open_time = int(bucket_open)
                st.minutes.clear()

        return out


def rollup_closed_candles(
    *,
    base_timeframe: str,
    derived_timeframe: str,
    base_candles: list[CandleClosed],
) -> list[CandleClosed]:
    """
    Pure function used for backfill: derive closed candles from a closed base-candle list.
    """
    base_s = timeframe_to_seconds(base_timeframe)
    tf_s = timeframe_to_seconds(derived_timeframe)
    if base_s <= 0 or tf_s <= 0 or tf_s % base_s != 0:
        return []

    candles_sorted = base_candles[:]
    candles_sorted.sort(key=lambda c: int(c.candle_time))

    bucket_size = int(tf_s // base_s)
    out: list[CandleClosed] = []
    buf: dict[int, CandleClosed] = {}
    cur_bucket_open: int | None = None

    for c in candles_sorted:
        t = int(c.candle_time)
        bucket_open = _align_bucket_open(t=t, tf_s=tf_s)
        if cur_bucket_open is None or int(cur_bucket_open) != int(bucket_open):
            buf.clear()
            cur_bucket_open = int(bucket_open)
        buf[t] = c

        expected_times = [int(bucket_open) + i * int(base_s) for i in range(bucket_size)]
        if not all(et in buf for et in expected_times):
            continue

        minutes = [buf[et] for et in expected_times]
        out.append(_merge_candles_to_derived(bucket_open_time=int(bucket_open), minutes=minutes))
        buf.clear()

    return out
