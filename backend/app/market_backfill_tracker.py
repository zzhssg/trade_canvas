from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal
from typing import cast

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
    def __init__(self, *, state_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._state_path = state_path
        self._states: dict[str, _MutableBackfillState] = {}
        self._load_from_disk()

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> _MutableBackfillState:
        state_raw = str(payload.get("state") or "idle")
        state = state_raw if state_raw in {"idle", "running", "succeeded", "failed"} else "idle"
        return _MutableBackfillState(
            state=cast(BackfillState, state),
            started_at=int(payload["started_at"]) if payload.get("started_at") is not None else None,
            updated_at=int(payload["updated_at"]) if payload.get("updated_at") is not None else None,
            start_missing_seconds=max(0, int(payload.get("start_missing_seconds") or 0)),
            start_missing_candles=max(0, int(payload.get("start_missing_candles") or 0)),
            current_missing_seconds=max(0, int(payload.get("current_missing_seconds") or 0)),
            current_missing_candles=max(0, int(payload.get("current_missing_candles") or 0)),
            reason=None if payload.get("reason") is None else str(payload.get("reason")),
            note=None if payload.get("note") is None else str(payload.get("note")),
            error=None if payload.get("error") is None else str(payload.get("error")),
        )

    def _load_from_disk(self) -> None:
        path = self._state_path
        if path is None or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        states_payload = payload.get("states")
        if not isinstance(states_payload, dict):
            return
        loaded: dict[str, _MutableBackfillState] = {}
        for series_id, state_payload in states_payload.items():
            if not isinstance(series_id, str) or not series_id:
                continue
            if not isinstance(state_payload, dict):
                continue
            try:
                loaded[series_id] = self._from_payload(state_payload)
            except Exception:
                continue
        with self._lock:
            self._states = loaded

    @staticmethod
    def _state_to_payload(state: _MutableBackfillState) -> dict[str, Any]:
        return {
            "state": str(state.state),
            "started_at": None if state.started_at is None else int(state.started_at),
            "updated_at": None if state.updated_at is None else int(state.updated_at),
            "start_missing_seconds": max(0, int(state.start_missing_seconds)),
            "start_missing_candles": max(0, int(state.start_missing_candles)),
            "current_missing_seconds": max(0, int(state.current_missing_seconds)),
            "current_missing_candles": max(0, int(state.current_missing_candles)),
            "reason": state.reason,
            "note": state.note,
            "error": state.error,
        }

    def _persist_locked(self) -> None:
        path = self._state_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "states": {
                    series_id: self._state_to_payload(state)
                    for series_id, state in sorted(self._states.items(), key=lambda item: str(item[0]))
                },
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
        except Exception:
            return

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
            self._persist_locked()

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
            self._persist_locked()

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
            self._persist_locked()

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
            self._persist_locked()

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
