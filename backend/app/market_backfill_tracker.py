from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

BackfillState = Literal["idle", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class BackfillProgressSnapshot:
    series_id: str
    state: BackfillState
    started_at: int | None
    updated_at: int | None
    start_missing_seconds: int
    start_missing_candles: int
    current_missing_seconds: int
    current_missing_candles: int
    progress_pct: float | None
    reason: str | None
    note: str | None
    error: str | None


@dataclass
class _MutableBackfillState:
    state: BackfillState = "idle"
    started_at: int | None = None
    updated_at: int | None = None
    start_missing_seconds: int = 0
    start_missing_candles: int = 0
    current_missing_seconds: int = 0
    current_missing_candles: int = 0
    reason: str | None = None
    note: str | None = None
    error: str | None = None


def _calc_progress_pct(*, start_missing_seconds: int, current_missing_seconds: int) -> float | None:
    start = max(0, int(start_missing_seconds))
    cur = max(0, int(current_missing_seconds))
    if start <= 0:
        return 100.0 if cur <= 0 else None
    done = max(0, start - cur)
    pct = (float(done) / float(start)) * 100.0
    return max(0.0, min(100.0, pct))


class MarketBackfillProgressTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, _MutableBackfillState] = {}

    @staticmethod
    def _now(now_time: int | None) -> int:
        return int(now_time) if now_time is not None else int(time.time())

    def begin(
        self,
        *,
        series_id: str,
        start_missing_seconds: int,
        start_missing_candles: int,
        reason: str,
        now_time: int | None = None,
    ) -> None:
        now = self._now(now_time)
        with self._lock:
            state = self._states.setdefault(series_id, _MutableBackfillState())
            state.state = "running"
            state.started_at = now
            state.updated_at = now
            state.start_missing_seconds = max(0, int(start_missing_seconds))
            state.start_missing_candles = max(0, int(start_missing_candles))
            state.current_missing_seconds = max(0, int(start_missing_seconds))
            state.current_missing_candles = max(0, int(start_missing_candles))
            state.reason = str(reason)
            state.note = None
            state.error = None

    def update(
        self,
        *,
        series_id: str,
        current_missing_seconds: int,
        current_missing_candles: int,
        note: str | None = None,
        now_time: int | None = None,
    ) -> None:
        now = self._now(now_time)
        with self._lock:
            state = self._states.setdefault(series_id, _MutableBackfillState())
            if state.started_at is None:
                state.started_at = now
            if state.state == "idle":
                state.state = "running"
            state.updated_at = now
            state.current_missing_seconds = max(0, int(current_missing_seconds))
            state.current_missing_candles = max(0, int(current_missing_candles))
            if note:
                state.note = str(note)

    def succeed(
        self,
        *,
        series_id: str,
        current_missing_seconds: int,
        current_missing_candles: int,
        note: str | None = None,
        now_time: int | None = None,
    ) -> None:
        now = self._now(now_time)
        with self._lock:
            state = self._states.setdefault(series_id, _MutableBackfillState())
            if state.started_at is None:
                state.started_at = now
            state.state = "succeeded"
            state.updated_at = now
            state.current_missing_seconds = max(0, int(current_missing_seconds))
            state.current_missing_candles = max(0, int(current_missing_candles))
            state.note = str(note) if note else state.note
            state.error = None

    def fail(
        self,
        *,
        series_id: str,
        current_missing_seconds: int,
        current_missing_candles: int,
        error: str,
        note: str | None = None,
        now_time: int | None = None,
    ) -> None:
        now = self._now(now_time)
        with self._lock:
            state = self._states.setdefault(series_id, _MutableBackfillState())
            if state.started_at is None:
                state.started_at = now
            state.state = "failed"
            state.updated_at = now
            state.current_missing_seconds = max(0, int(current_missing_seconds))
            state.current_missing_candles = max(0, int(current_missing_candles))
            state.error = str(error)
            state.note = str(note) if note else state.note

    def snapshot(self, *, series_id: str) -> BackfillProgressSnapshot:
        with self._lock:
            state = self._states.get(series_id, _MutableBackfillState())
            progress = _calc_progress_pct(
                start_missing_seconds=int(state.start_missing_seconds),
                current_missing_seconds=int(state.current_missing_seconds),
            )
            return BackfillProgressSnapshot(
                series_id=series_id,
                state=state.state,
                started_at=state.started_at,
                updated_at=state.updated_at,
                start_missing_seconds=max(0, int(state.start_missing_seconds)),
                start_missing_candles=max(0, int(state.start_missing_candles)),
                current_missing_seconds=max(0, int(state.current_missing_seconds)),
                current_missing_candles=max(0, int(state.current_missing_candles)),
                progress_pct=progress,
                reason=state.reason,
                note=state.note,
                error=state.error,
            )
