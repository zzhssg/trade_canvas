from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .factor_store import FactorStore
from .overlay_store import OverlayStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class OverlaySettings:
    window_candles: int = 2000


class OverlayOrchestrator:
    """
    v0 overlay orchestrator:
    - Reads FactorStore (pivot.major/minor, pen.confirmed)
    - Builds overlay instructions and persists them to OverlayStore as versioned defs.
    - instruction_catalog_patch is derived from version_id cursor.
    """

    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        overlay_store: OverlayStore,
        settings: OverlaySettings | None = None,
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._overlay_store = overlay_store
        self._settings = settings or OverlaySettings()

    def enabled(self) -> bool:
        raw = os.environ.get("TRADE_CANVAS_ENABLE_OVERLAY_INGEST", "1")
        return _truthy_flag(raw)

    def _load_window_candles(self) -> int:
        raw = (os.environ.get("TRADE_CANVAS_OVERLAY_WINDOW_CANDLES") or "").strip()
        if not raw:
            return int(self._settings.window_candles)
        try:
            return max(100, int(raw))
        except ValueError:
            return int(self._settings.window_candles)

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        """
        Build overlay instructions up to `up_to_candle_time` (closed only).
        """
        if not self.enabled():
            return

        to_time = int(up_to_candle_time or 0)
        if to_time <= 0:
            return

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        window_candles = self._load_window_candles()
        cutoff_time = max(0, to_time - int(window_candles) * int(tf_s))

        factor_rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(cutoff_time),
            end_candle_time=int(to_time),
            limit=50000,
        )

        pivot_major: list[dict[str, Any]] = []
        pivot_minor: list[dict[str, Any]] = []
        pen_confirmed: list[dict[str, Any]] = []
        for r in factor_rows:
            if r.factor_name == "pivot" and r.kind == "pivot.major":
                pivot_major.append(dict(r.payload or {}))
            elif r.factor_name == "pivot" and r.kind == "pivot.minor":
                pivot_minor.append(dict(r.payload or {}))
            elif r.factor_name == "pen" and r.kind == "pen.confirmed":
                pen_confirmed.append(dict(r.payload or {}))

        # Build marker instructions (append-only per instruction_id).
        marker_defs: list[tuple[str, str, int, dict[str, Any]]] = []
        for level, items, alpha in (
            ("pivot.major", pivot_major, 1.0),
            ("pivot.minor", pivot_minor, 0.6),
        ):
            for p in items:
                pivot_time = int(p.get("pivot_time") or 0)
                visible_time = int(p.get("visible_time") or 0)
                direction = str(p.get("direction") or "")
                window = int(p.get("window") or 0)
                if pivot_time <= 0 or visible_time <= 0:
                    continue
                if pivot_time < cutoff_time or pivot_time > to_time:
                    continue
                if direction not in {"support", "resistance"}:
                    continue

                instruction_id = f"{level}:{pivot_time}:{direction}:{window}"
                color = "#ef4444" if direction == "resistance" else "#22c55e"
                if alpha < 1.0:
                    color = f"rgba(239,68,68,{alpha})" if direction == "resistance" else f"rgba(34,197,94,{alpha})"
                marker_defs.append(
                    (
                        instruction_id,
                        "marker",
                        int(visible_time),
                        {
                            "type": "marker",
                            "feature": level,
                            "time": int(pivot_time),
                            "position": "aboveBar" if direction == "resistance" else "belowBar",
                            "color": color,
                            "shape": "circle",
                            # Keep the field for schema stability, but do not render a letter label.
                            "text": "",
                            "size": 1.0 if level == "pivot.major" else 0.6,
                        },
                    )
                )

        # Build pen polyline instruction (single id, versioned).
        pen_confirmed.sort(key=lambda d: (int(d.get("start_time") or 0), int(d.get("visible_time") or 0)))
        points: list[dict[str, Any]] = []
        for item in pen_confirmed:
            st = int(item.get("start_time") or 0)
            et = int(item.get("end_time") or 0)
            sp = float(item.get("start_price") or 0.0)
            ep = float(item.get("end_price") or 0.0)
            if st <= 0 or et <= 0:
                continue
            if et < cutoff_time or st > to_time:
                continue
            if not points or points[-1].get("time") != st:
                points.append({"time": st, "value": sp})
            points.append({"time": et, "value": ep})

        pen_def: dict[str, Any] | None = None
        if points:
            pen_def = {
                "type": "polyline",
                "feature": "pen.confirmed",
                "points": list(points),
                "color": "#a78bfa",
                "lineWidth": 2,
            }

        with self._overlay_store.connect() as conn:
            for instruction_id, kind, visible_time, payload in marker_defs:
                prev = self._overlay_store.get_latest_def_for_instruction_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                )
                if prev == payload:
                    continue
                self._overlay_store.insert_instruction_version_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    kind=kind,
                    visible_time=visible_time,
                    payload=payload,
                )

            if pen_def is not None:
                prev = self._overlay_store.get_latest_def_for_instruction_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id="pen.confirmed",
                )
                if prev != pen_def:
                    self._overlay_store.insert_instruction_version_in_conn(
                        conn,
                        series_id=series_id,
                        instruction_id="pen.confirmed",
                        kind="polyline",
                        visible_time=int(to_time),
                        payload=pen_def,
                    )

            self._overlay_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(to_time))
            conn.commit()
