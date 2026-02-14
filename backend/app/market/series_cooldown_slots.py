from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass(frozen=True)
class SeriesCooldownSlots:
    cooldown_seconds: float = 2.0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
    _state: dict[str, tuple[bool, int, float]] = field(default_factory=dict, init=False, repr=False, compare=False)

    def _cooldown(self) -> float:
        return max(0.1, float(self.cooldown_seconds))

    def try_acquire(self, *, series_id: str) -> bool:
        sid = str(series_id)
        now = float(time.monotonic())
        with self._lock:
            in_flight, last_target_time, last_run = self._state.get(sid, (False, 0, 0.0))
            if bool(in_flight):
                return False
            if now - float(last_run) < self._cooldown():
                return False
            self._state[sid] = (True, int(last_target_time), now)
            return True

    def release(self, *, series_id: str) -> None:
        sid = str(series_id)
        now = float(time.monotonic())
        with self._lock:
            _, last_target_time, last_run = self._state.get(sid, (False, 0, 0.0))
            self._state[sid] = (False, int(last_target_time), max(float(last_run), now))

    def try_acquire_target(self, *, series_id: str, target_time: int) -> bool:
        sid = str(series_id)
        target = int(target_time)
        now = float(time.monotonic())
        with self._lock:
            in_flight, last_target_time, last_run = self._state.get(sid, (False, 0, 0.0))
            if bool(in_flight):
                return False
            same_or_older_target = int(target) <= int(last_target_time)
            if same_or_older_target and now - float(last_run) < self._cooldown():
                return False
            self._state[sid] = (True, max(int(last_target_time), int(target)), now)
            return True

    def release_target(self, *, series_id: str, target_time: int) -> None:
        sid = str(series_id)
        target = int(target_time)
        now = float(time.monotonic())
        with self._lock:
            _, last_target_time, _ = self._state.get(sid, (False, 0, 0.0))
            self._state[sid] = (False, max(int(last_target_time), int(target)), now)
