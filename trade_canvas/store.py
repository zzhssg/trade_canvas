from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self


@dataclass(frozen=True)
class LatestLedgerRow:
    candle_id: str
    candle_time: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class OverlayEventRow:
    candle_id: str
    candle_time: int
    kind: str
    payload: dict[str, Any]
    id: int | None = None


@dataclass(frozen=True)
class PlotPointRow:
    feature_key: str
    candle_time: int
    value: float


@dataclass
class _KernelStoreState:
    candles_by_series: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    kernel_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    ledger_latest: dict[str, LatestLedgerRow] = field(default_factory=dict)
    overlay_events: dict[str, list[OverlayEventRow]] = field(default_factory=dict)
    plot_points: dict[str, dict[str, dict[int, PlotPointRow]]] = field(default_factory=dict)
    next_overlay_event_id: int = 1


_STORE_STATES: dict[str, _KernelStoreState] = {}
_STORE_STATES_LOCK = threading.Lock()


def _store_key(db_path: str | Path) -> str:
    return str(Path(db_path))


def _get_store_state(db_path: str | Path) -> _KernelStoreState:
    key = _store_key(db_path)
    with _STORE_STATES_LOCK:
        state = _STORE_STATES.get(key)
        if state is None:
            state = _KernelStoreState()
            _STORE_STATES[key] = state
        return state


def _series_key(symbol: str, timeframe: str) -> str:
    return f"{str(symbol)}:{str(timeframe)}"


def _clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, separators=(",", ":"), sort_keys=True))


class KernelStoreConnection:
    def __init__(self, state: _KernelStoreState) -> None:
        self._state = state
        self.total_changes = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class KernelStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def connect(self) -> KernelStoreConnection:
        return KernelStoreConnection(_get_store_state(self._db_path))

    def init_schema(self, conn: KernelStoreConnection) -> None:
        conn.commit()

    def upsert_candle(self, conn: KernelStoreConnection, *, candle: Any) -> None:
        series = _series_key(str(candle.symbol), str(candle.timeframe))
        by_time = conn._state.candles_by_series.setdefault(series, {})
        by_time[int(candle.open_time)] = {
            "candle_id": str(candle.candle_id),
            "symbol": str(candle.symbol),
            "timeframe": str(candle.timeframe),
            "open_time": int(candle.open_time),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
        }
        conn.total_changes += 1

    def get_latest_candle_id(self, conn: KernelStoreConnection, *, symbol: str, timeframe: str) -> str | None:
        by_time = conn._state.candles_by_series.get(_series_key(symbol, timeframe), {})
        if not by_time:
            return None
        latest_time = max(by_time)
        return str(by_time[int(latest_time)]["candle_id"])

    def get_latest_candle_time(self, conn: KernelStoreConnection, *, symbol: str, timeframe: str) -> int | None:
        by_time = conn._state.candles_by_series.get(_series_key(symbol, timeframe), {})
        if not by_time:
            return None
        return int(max(by_time))

    def load_state(self, conn: KernelStoreConnection, *, key: str) -> dict[str, Any] | None:
        payload = conn._state.kernel_state.get(str(key))
        if payload is None:
            return None
        return _clone_payload(payload)

    def save_state(self, conn: KernelStoreConnection, *, key: str, payload: dict[str, Any]) -> None:
        conn._state.kernel_state[str(key)] = _clone_payload(payload)
        conn.total_changes += 1

    def set_latest_ledger(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        candle_id: str,
        candle_time: int,
        payload: dict[str, Any],
    ) -> None:
        conn._state.ledger_latest[_series_key(symbol, timeframe)] = LatestLedgerRow(
            candle_id=str(candle_id),
            candle_time=int(candle_time),
            payload=_clone_payload(payload),
        )
        conn.total_changes += 1

    def get_latest_ledger(self, conn: KernelStoreConnection, *, symbol: str, timeframe: str) -> LatestLedgerRow | None:
        row = conn._state.ledger_latest.get(_series_key(symbol, timeframe))
        if row is None:
            return None
        return LatestLedgerRow(
            candle_id=str(row.candle_id),
            candle_time=int(row.candle_time),
            payload=_clone_payload(row.payload),
        )

    def append_overlay_event(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        candle_id: str,
        candle_time: int,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        series = _series_key(symbol, timeframe)
        event_id = int(conn._state.next_overlay_event_id)
        conn._state.next_overlay_event_id += 1
        events = conn._state.overlay_events.setdefault(series, [])
        events.append(
            OverlayEventRow(
                id=event_id,
                candle_id=str(candle_id),
                candle_time=int(candle_time),
                kind=str(kind),
                payload=_clone_payload(payload),
            )
        )
        conn.total_changes += 1

    def get_latest_overlay_event(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        kind: str,
    ) -> OverlayEventRow | None:
        events = conn._state.overlay_events.get(_series_key(symbol, timeframe), [])
        candidates = [event for event in events if str(event.kind) == str(kind)]
        if not candidates:
            return None
        latest = max(candidates, key=lambda event: (int(event.candle_time), int(event.id or 0)))
        return OverlayEventRow(
            id=int(latest.id or 0),
            candle_id=str(latest.candle_id),
            candle_time=int(latest.candle_time),
            kind=str(latest.kind),
            payload=_clone_payload(latest.payload),
        )

    def get_latest_overlay_event_id(self, conn: KernelStoreConnection, *, symbol: str, timeframe: str) -> int | None:
        events = conn._state.overlay_events.get(_series_key(symbol, timeframe), [])
        if not events:
            return None
        return int(max(int(event.id or 0) for event in events))

    def get_overlay_events_since_id(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        since_id: int | None,
        limit: int = 5000,
    ) -> list[OverlayEventRow]:
        events = conn._state.overlay_events.get(_series_key(symbol, timeframe), [])
        min_event_id = 0 if since_id is None else int(since_id)
        out = [event for event in events if int(event.id or 0) > min_event_id]
        out.sort(key=lambda event: int(event.id or 0))
        if int(limit) > 0:
            out = out[: int(limit)]
        return [
            OverlayEventRow(
                id=int(event.id or 0),
                candle_id=str(event.candle_id),
                candle_time=int(event.candle_time),
                kind=str(event.kind),
                payload=_clone_payload(event.payload),
            )
            for event in out
        ]

    def upsert_plot_point(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        feature_key: str,
        candle_id: str,
        candle_time: int,
        value: float,
    ) -> None:
        series = _series_key(symbol, timeframe)
        by_feature = conn._state.plot_points.setdefault(series, {})
        by_time = by_feature.setdefault(str(feature_key), {})
        by_time[int(candle_time)] = PlotPointRow(
            feature_key=str(feature_key),
            candle_time=int(candle_time),
            value=float(value),
        )
        conn.total_changes += 1

    def get_plot_points_since_time(
        self,
        conn: KernelStoreConnection,
        *,
        symbol: str,
        timeframe: str,
        feature_keys: list[str],
        since_time: int | None,
        limit: int = 5000,
    ) -> list[PlotPointRow]:
        if not feature_keys:
            return []
        series = _series_key(symbol, timeframe)
        by_feature = conn._state.plot_points.get(series, {})
        floor = -1 if since_time is None else int(since_time)

        out: list[PlotPointRow] = []
        for feature_key in feature_keys:
            by_time = by_feature.get(str(feature_key), {})
            for candle_time, point in by_time.items():
                if int(candle_time) <= floor:
                    continue
                out.append(
                    PlotPointRow(
                        feature_key=str(point.feature_key),
                        candle_time=int(point.candle_time),
                        value=float(point.value),
                    )
                )

        out.sort(key=lambda point: (int(point.candle_time), str(point.feature_key)))
        if int(limit) > 0:
            out = out[: int(limit)]
        return out
