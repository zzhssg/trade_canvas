from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Mapping


def _normalize_labels(labels: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return tuple()
    pairs: list[tuple[str, str]] = []
    for key, value in labels.items():
        k = str(key).strip()
        if not k:
            continue
        pairs.append((k, str(value)))
    pairs.sort(key=lambda item: item[0])
    return tuple(pairs)


def _metric_key(name: str, labels: Mapping[str, object] | None = None) -> str:
    normalized_name = str(name).strip()
    normalized_labels = _normalize_labels(labels)
    if not normalized_labels:
        return normalized_name
    labels_str = ",".join(f"{key}={value}" for key, value in normalized_labels)
    return f"{normalized_name}{{{labels_str}}}"


@dataclass
class _TimerStat:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0


class RuntimeMetrics:
    def __init__(self, *, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self._updated_at_ms = 0
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, _TimerStat] = {}

    def enabled(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def incr(self, name: str, *, value: float = 1.0, labels: Mapping[str, object] | None = None) -> None:
        if not self._enabled:
            return
        metric_key = _metric_key(name, labels)
        delta = float(value)
        with self._lock:
            current = float(self._counters.get(metric_key, 0.0))
            self._counters[metric_key] = current + delta
            self._updated_at_ms = self._now_ms()

    def set_gauge(self, name: str, *, value: float, labels: Mapping[str, object] | None = None) -> None:
        if not self._enabled:
            return
        metric_key = _metric_key(name, labels)
        with self._lock:
            self._gauges[metric_key] = float(value)
            self._updated_at_ms = self._now_ms()

    def observe_ms(self, name: str, *, duration_ms: float, labels: Mapping[str, object] | None = None) -> None:
        if not self._enabled:
            return
        metric_key = _metric_key(name, labels)
        value = max(0.0, float(duration_ms))
        with self._lock:
            stat = self._timers.get(metric_key)
            if stat is None:
                stat = _TimerStat()
                self._timers[metric_key] = stat
            stat.count += 1
            stat.total_ms += value
            stat.max_ms = max(float(stat.max_ms), value)
            self._updated_at_ms = self._now_ms()

    def snapshot(self) -> dict:
        with self._lock:
            counters = {key: float(value) for key, value in sorted(self._counters.items(), key=lambda item: item[0])}
            gauges = {key: float(value) for key, value in sorted(self._gauges.items(), key=lambda item: item[0])}
            timers: dict[str, dict[str, float]] = {}
            for key, stat in sorted(self._timers.items(), key=lambda item: item[0]):
                avg_ms = float(stat.total_ms) / float(stat.count) if int(stat.count) > 0 else 0.0
                timers[key] = {
                    "count": float(stat.count),
                    "total_ms": float(stat.total_ms),
                    "max_ms": float(stat.max_ms),
                    "avg_ms": float(avg_ms),
                }
            return {
                "enabled": bool(self._enabled),
                "updated_at_ms": int(self._updated_at_ms),
                "counters": counters,
                "gauges": gauges,
                "timers": timers,
            }
