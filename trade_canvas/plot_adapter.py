from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import OverlayEventRow, PlotPointRow, SqliteStore


@dataclass(frozen=True)
class PlotCursor:
    candle_time: int | None
    overlay_event_id: int | None


@dataclass(frozen=True)
class PlotDeltaResult:
    ok: bool
    reason: str | None
    to_candle_id: str | None
    to_candle_time: int | None
    lines: dict[str, list[dict[str, Any]]]
    overlay_events: list[OverlayEventRow]
    next_cursor: PlotCursor | None


class PlotDeltaAdapter:
    """
    Incremental "plot read" adapter:
    - Enforces candle_id alignment (latest candle vs latest ledger)
    - Returns only incremental plot points and overlay events since a cursor
    """

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def get_delta(
        self,
        conn,
        *,
        symbol: str,
        timeframe: str,
        feature_keys: list[str],
        cursor: PlotCursor | None,
        limit: int = 5000,
    ) -> PlotDeltaResult:
        latest_candle_id = self._store.get_latest_candle_id(conn, symbol=symbol, timeframe=timeframe)
        latest_ledger = self._store.get_latest_ledger(conn, symbol=symbol, timeframe=timeframe)
        if latest_candle_id is None or latest_ledger is None:
            return PlotDeltaResult(
                ok=False,
                reason="not_ready",
                to_candle_id=None,
                to_candle_time=None,
                lines={},
                overlay_events=[],
                next_cursor=None,
            )

        if latest_ledger.candle_id != latest_candle_id:
            return PlotDeltaResult(
                ok=False,
                reason="candle_id_mismatch",
                to_candle_id=None,
                to_candle_time=None,
                lines={},
                overlay_events=[],
                next_cursor=None,
            )

        since_time = None if cursor is None else cursor.candle_time
        since_event_id = None if cursor is None else cursor.overlay_event_id

        points = self._store.get_plot_points_since_time(
            conn,
            symbol=symbol,
            timeframe=timeframe,
            feature_keys=feature_keys,
            since_time=since_time,
            limit=limit,
        )
        lines: dict[str, list[dict[str, Any]]] = {k: [] for k in feature_keys}
        for p in points:
            lines.setdefault(p.feature_key, []).append({"time": p.candle_time, "value": p.value})

        events = self._store.get_overlay_events_since_id(
            conn,
            symbol=symbol,
            timeframe=timeframe,
            since_id=since_event_id,
            limit=limit,
        )
        latest_event_id = self._store.get_latest_overlay_event_id(conn, symbol=symbol, timeframe=timeframe)
        next_event_id = latest_event_id if latest_event_id is not None else since_event_id

        next_cursor = PlotCursor(candle_time=latest_ledger.candle_time, overlay_event_id=next_event_id)
        return PlotDeltaResult(
            ok=True,
            reason=None,
            to_candle_id=latest_ledger.candle_id,
            to_candle_time=latest_ledger.candle_time,
            lines=lines,
            overlay_events=events,
            next_cursor=next_cursor,
        )


def group_line_points(points: list[PlotPointRow]) -> dict[str, list[dict[str, Any]]]:
    """
    Helper for callers that want to bypass PlotDeltaAdapter and shape the SQL rows into
    lightweight-charts-friendly line series points.
    """

    out: dict[str, list[dict[str, Any]]] = {}
    for p in points:
        out.setdefault(p.feature_key, []).append({"time": p.candle_time, "value": p.value})
    return out

