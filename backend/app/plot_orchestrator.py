from __future__ import annotations

import os
from dataclasses import dataclass

from .pivot import compute_major_pivots, compute_minor_pivots
from .plot_store import OverlayEventWrite, PlotStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PivotSettings:
    window_major: int = 50
    window_minor: int = 5
    lookback_candles: int = 5000


class PlotOrchestrator:
    """
    v0 plot orchestrator:
    - Triggered only by closed candles (finalized-only).
    - Builds plot artifacts (currently pivot events) and persists them to SQLite (PlotStore).
    - Delayed visibility: events are emitted at visible_time, but point is drawn at pivot_time.
    """

    def __init__(self, *, candle_store: CandleStore, plot_store: PlotStore, settings: PivotSettings | None = None) -> None:
        self._candle_store = candle_store
        self._plot_store = plot_store
        self._settings = settings or PivotSettings()

    def enabled(self) -> bool:
        # Default ON for v0 (can be disabled for perf/debug).
        raw = os.environ.get("TRADE_CANVAS_ENABLE_PLOT_INGEST", "1")
        return _truthy_flag(raw)

    def _load_settings(self) -> PivotSettings:
        major_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MAJOR") or "").strip()
        minor_raw = (os.environ.get("TRADE_CANVAS_PIVOT_WINDOW_MINOR") or "").strip()
        lookback_raw = (os.environ.get("TRADE_CANVAS_PLOT_LOOKBACK_CANDLES") or "").strip()
        major = self._settings.window_major
        minor = self._settings.window_minor
        lookback = self._settings.lookback_candles
        if major_raw:
            try:
                major = max(1, int(major_raw))
            except ValueError:
                major = self._settings.window_major
        if minor_raw:
            try:
                minor = max(1, int(minor_raw))
            except ValueError:
                minor = self._settings.window_minor
        if lookback_raw:
            try:
                lookback = max(100, int(lookback_raw))
            except ValueError:
                lookback = self._settings.lookback_candles
        return PivotSettings(window_major=int(major), window_minor=int(minor), lookback_candles=int(lookback))

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        if not self.enabled():
            return

        up_to = int(up_to_candle_time or 0)
        if up_to <= 0:
            return

        s = self._load_settings()
        candles = self._candle_store.get_closed(series_id, since=None, limit=int(s.lookback_candles))
        if not candles:
            return

        # Only compute pivots for confirmed/available candles up to up_to (tail may include older).
        # The list is ascending; find last index <= up_to.
        last_idx = -1
        for i, c in enumerate(candles):
            if int(c.candle_time) <= up_to:
                last_idx = i
        if last_idx < 0:
            return
        candles = candles[: last_idx + 1]

        majors = compute_major_pivots(candles, window=int(s.window_major))
        minors = compute_minor_pivots(candles, window=int(s.window_minor))

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        # Defensive: ensure delay semantics roughly match timeframe grid; do not enforce hard.
        _ = tf_s

        writes: list[OverlayEventWrite] = []
        for p in majors:
            visible_time = int(p.visible_time)
            writes.append(
                OverlayEventWrite(
                    series_id=series_id,
                    candle_time=visible_time,
                    kind="pivot.major",
                    candle_id=f"{series_id}:{visible_time}",
                    pivot_time=int(p.pivot_time),
                    direction=str(p.direction),
                    payload={
                        "pivot_time": int(p.pivot_time),
                        "pivot_price": float(p.pivot_price),
                        "direction": str(p.direction),
                        "visible_time": int(visible_time),
                        "window": int(p.window),
                        "level": "major",
                    },
                )
            )
        for p in minors:
            visible_time = int(p.visible_time)
            writes.append(
                OverlayEventWrite(
                    series_id=series_id,
                    candle_time=visible_time,
                    kind="pivot.minor",
                    candle_id=f"{series_id}:{visible_time}",
                    pivot_time=int(p.pivot_time),
                    direction=str(p.direction),
                    payload={
                        "pivot_time": int(p.pivot_time),
                        "pivot_price": float(p.pivot_price),
                        "direction": str(p.direction),
                        "visible_time": int(visible_time),
                        "window": int(p.window),
                        "level": "minor",
                    },
                )
            )

        with self._plot_store.connect() as conn:
            self._plot_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=up_to)
            self._plot_store.insert_overlay_events_in_conn(conn, events=writes)
            conn.commit()

