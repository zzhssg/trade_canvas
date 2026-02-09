from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from .anchor_semantics import build_anchor_history_from_switches
from .debug_hub import DebugHub
from .factor_slices import build_pen_head_candidate, build_pen_head_preview
from .factor_store import FactorStore
from .overlay_store import OverlayStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .zhongshu import build_alive_zhongshu_from_confirmed_pens


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
        self._debug_hub: DebugHub | None = None

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

    def enabled(self) -> bool:
        raw = os.environ.get("TRADE_CANVAS_ENABLE_OVERLAY_INGEST", "1")
        return _truthy_flag(raw)

    def reset_series(self, *, series_id: str) -> None:
        with self._overlay_store.connect() as conn:
            self._overlay_store.clear_series_in_conn(conn, series_id=series_id)
            conn.commit()

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
        t0 = time.perf_counter()
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
        zhongshu_dead: list[dict[str, Any]] = []
        anchor_switches: list[dict[str, Any]] = []
        for r in factor_rows:
            if r.factor_name == "pivot" and r.kind == "pivot.major":
                pivot_major.append(dict(r.payload or {}))
            elif r.factor_name == "pivot" and r.kind == "pivot.minor":
                pivot_minor.append(dict(r.payload or {}))
            elif r.factor_name == "pen" and r.kind == "pen.confirmed":
                pen_confirmed.append(dict(r.payload or {}))
            elif r.factor_name == "zhongshu" and r.kind == "zhongshu.dead":
                zhongshu_dead.append(dict(r.payload or {}))
            elif r.factor_name == "anchor" and r.kind == "anchor.switch":
                anchor_switches.append(dict(r.payload or {}))

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
                            "size": 1.0 if level == "pivot.major" else 0.5,
                        },
                    )
                )

        # Anchor switch markers.
        for sw in anchor_switches:
            switch_time = int(sw.get("switch_time") or 0)
            if switch_time <= 0:
                continue
            if switch_time < cutoff_time or switch_time > to_time:
                continue
            reason = str(sw.get("reason") or "switch")
            new_anchor = sw.get("new_anchor") if isinstance(sw.get("new_anchor"), dict) else {}
            direction = int(new_anchor.get("direction") or 0)
            position = "belowBar" if direction >= 0 else "aboveBar"
            shape = "arrowUp" if direction >= 0 else "arrowDown"
            instruction_id = f"anchor.switch:{switch_time}:{direction}:{reason}"
            marker_defs.append(
                (
                    instruction_id,
                    "marker",
                    int(switch_time),
                    {
                        "type": "marker",
                        "feature": "anchor.switch",
                        "time": int(switch_time),
                        "position": position,
                        "color": "#f59e0b",
                        "shape": shape,
                        "text": "A",
                        "size": 1.0,
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
                "color": "#ffffff",
                "lineWidth": 2,
            }

        # Zhongshu + Anchor polylines (v1).
        polyline_defs: list[tuple[str, int, dict[str, Any]]] = []
        pen_confirmed.sort(key=lambda d: (int(d.get("visible_time") or 0), int(d.get("start_time") or 0)))
        pen_lookup: dict[tuple[int, int, int], dict[str, Any]] = {}
        pen_latest_by_start_dir: dict[tuple[int, int], dict[str, Any]] = {}
        for p in pen_confirmed:
            start_time = int(p.get("start_time") or 0)
            end_time = int(p.get("end_time") or 0)
            direction = int(p.get("direction") or 0)
            key = (start_time, end_time, direction)
            pen_lookup[key] = p
            pointer_key = (start_time, direction)
            prev = pen_latest_by_start_dir.get(pointer_key)
            if prev is None or int(prev.get("end_time") or 0) <= end_time:
                pen_latest_by_start_dir[pointer_key] = p

        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(cutoff_time),
            end_time=int(to_time),
            limit=int(window_candles) + 10,
        )
        last_confirmed = pen_confirmed[-1] if pen_confirmed else None
        preview = build_pen_head_preview(candles=candles, major_pivots=pivot_major, aligned_time=int(to_time))
        pen_extending = preview.get("extending") if isinstance(preview.get("extending"), dict) else None
        pen_candidate = preview.get("candidate") if isinstance(preview.get("candidate"), dict) else None
        if pen_candidate is None:
            # Fallback for old data snapshots without enough major pivots in the current window.
            pen_candidate = build_pen_head_candidate(candles=candles, last_confirmed=last_confirmed, aligned_time=int(to_time))

        if pen_confirmed:
            try:
                alive = build_alive_zhongshu_from_confirmed_pens(pen_confirmed, up_to_visible_time=int(to_time))
            except Exception:
                alive = None
        else:
            alive = None

        def add_polyline(
            instruction_id: str,
            *,
            visible_time: int,
            feature: str,
            points: list[dict[str, Any]],
            color: str,
            line_width: int = 2,
            line_style: str | None = None,
            entry_direction: int | None = None,
        ) -> None:
            if len(points) < 2:
                return
            payload: dict[str, Any] = {
                "type": "polyline",
                "feature": feature,
                "points": points,
                "color": color,
                "lineWidth": int(line_width),
            }
            if line_style:
                payload["lineStyle"] = str(line_style)
            if entry_direction in {-1, 1}:
                payload["entryDirection"] = int(entry_direction)
            polyline_defs.append((instruction_id, int(visible_time), payload))

        def zhongshu_border_color(*, is_alive: bool, entry_direction: int) -> str:
            if is_alive:
                return "rgba(22,163,74,0.72)" if entry_direction >= 0 else "rgba(220,38,38,0.72)"
            return "rgba(74,222,128,0.58)" if entry_direction >= 0 else "rgba(248,113,113,0.58)"

        # Zhongshu dead boxes (rendered as top/bottom lines).
        for zs in zhongshu_dead:
            start_time = int(zs.get("start_time") or 0)
            end_time = int(zs.get("end_time") or 0)
            zg = float(zs.get("zg") or 0.0)
            zd = float(zs.get("zd") or 0.0)
            visible_time = int(zs.get("visible_time") or 0)
            entry_direction = int(zs.get("entry_direction") or -1)
            if start_time <= 0 or end_time <= 0 or visible_time <= 0:
                continue
            if end_time < cutoff_time or start_time > to_time:
                continue
            base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
            border_color = zhongshu_border_color(is_alive=False, entry_direction=entry_direction)
            add_polyline(
                f"{base_id}:top",
                visible_time=visible_time,
                feature="zhongshu.dead",
                points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
                color=border_color,
                entry_direction=entry_direction,
            )
            add_polyline(
                f"{base_id}:bottom",
                visible_time=visible_time,
                feature="zhongshu.dead",
                points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
                color=border_color,
                entry_direction=entry_direction,
            )

        # Zhongshu alive (single evolving box).
        if alive is not None and int(alive.visible_time) == int(to_time):
            start_time = int(alive.start_time)
            end_time = int(alive.end_time)
            zg = float(alive.zg)
            zd = float(alive.zd)
            entry_direction = int(alive.entry_direction) if int(alive.entry_direction) in {-1, 1} else 1
            border_color = zhongshu_border_color(is_alive=True, entry_direction=entry_direction)
            add_polyline(
                "zhongshu.alive:top",
                visible_time=int(to_time),
                feature="zhongshu.alive",
                points=[{"time": start_time, "value": zg}, {"time": end_time, "value": zg}],
                color=border_color,
                entry_direction=entry_direction,
            )
            add_polyline(
                "zhongshu.alive:bottom",
                visible_time=int(to_time),
                feature="zhongshu.alive",
                points=[{"time": start_time, "value": zd}, {"time": end_time, "value": zd}],
                color=border_color,
                entry_direction=entry_direction,
            )

        history_anchors, history_switches = build_anchor_history_from_switches(anchor_switches)

        # Anchor current + history (polyline).
        current_ref = None
        if history_switches:
            cur = history_switches[-1].get("new_anchor")
            if isinstance(cur, dict):
                current_ref = cur
        elif last_confirmed is not None:
            current_ref = {
                "kind": "confirmed",
                "start_time": int(last_confirmed.get("start_time") or 0),
                "end_time": int(last_confirmed.get("end_time") or 0),
                "direction": int(last_confirmed.get("direction") or 0),
            }

        def resolve_points(ref: dict | None) -> list[dict[str, Any]]:
            if not ref:
                return []
            kind = str(ref.get("kind") or "")
            start_time = int(ref.get("start_time") or 0)
            end_time = int(ref.get("end_time") or 0)
            direction = int(ref.get("direction") or 0)
            if start_time <= 0 or end_time <= 0:
                return []
            if kind == "candidate" and isinstance(pen_candidate, dict):
                if (
                    int(pen_candidate.get("start_time") or 0) == start_time
                    and int(pen_candidate.get("end_time") or 0) == end_time
                    and int(pen_candidate.get("direction") or 0) == direction
                ):
                    return [
                        {"time": start_time, "value": float(pen_candidate.get("start_price") or 0.0)},
                        {"time": end_time, "value": float(pen_candidate.get("end_price") or 0.0)},
                    ]
            match = pen_lookup.get((start_time, end_time, direction))
            if match is None:
                match = pen_latest_by_start_dir.get((start_time, direction))
            if match is None:
                return []
            return [
                {"time": int(match.get("start_time") or 0), "value": float(match.get("start_price") or 0.0)},
                {"time": int(match.get("end_time") or 0), "value": float(match.get("end_price") or 0.0)},
            ]

        anchor_points = resolve_points(current_ref)
        if anchor_points:
            add_polyline(
                "anchor.current",
                visible_time=int(to_time),
                feature="anchor.current",
                points=anchor_points,
                color="#f59e0b",
            )

        for idx, anchor_ref in enumerate(history_anchors):
            history_points = resolve_points(anchor_ref)
            if not history_points:
                continue
            switch_payload = history_switches[idx]
            switch_time = int(switch_payload.get("switch_time") or to_time)
            instruction_id = (
                f"anchor.history:{switch_time}:{int(anchor_ref.get('start_time') or 0)}:"
                f"{int(anchor_ref.get('end_time') or 0)}:{int(anchor_ref.get('direction') or 0)}"
            )
            add_polyline(
                instruction_id,
                visible_time=max(1, switch_time),
                feature="anchor.history",
                points=history_points,
                color="rgba(59,130,246,0.55)",
                line_width=1,
            )

        if isinstance(pen_extending, dict):
            add_polyline(
                "pen.extending",
                visible_time=int(to_time),
                feature="pen.extending",
                points=[
                    {"time": int(pen_extending.get("start_time") or 0), "value": float(pen_extending.get("start_price") or 0.0)},
                    {"time": int(pen_extending.get("end_time") or 0), "value": float(pen_extending.get("end_price") or 0.0)},
                ],
                color="#ffffff",
                line_style="dashed",
            )

        if isinstance(pen_candidate, dict):
            add_polyline(
                "pen.candidate",
                visible_time=int(to_time),
                feature="pen.candidate",
                points=[
                    {"time": int(pen_candidate.get("start_time") or 0), "value": float(pen_candidate.get("start_price") or 0.0)},
                    {"time": int(pen_candidate.get("end_time") or 0), "value": float(pen_candidate.get("end_price") or 0.0)},
                ],
                color="#ffffff",
                line_style="dashed",
            )

        with self._overlay_store.connect() as conn:
            before_changes = int(conn.total_changes)
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

            for instruction_id, visible_time, payload in polyline_defs:
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
                    kind="polyline",
                    visible_time=int(visible_time),
                    payload=payload,
                )

            self._overlay_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(to_time))
            conn.commit()
            wrote = int(conn.total_changes) - before_changes

        if self._debug_hub is not None:
            self._debug_hub.emit(
                pipe="write",
                event="write.overlay.ingest_done",
                series_id=series_id,
                message="overlay ingest done",
                data={
                    "up_to_candle_time": int(to_time),
                    "cutoff_time": int(cutoff_time),
                    "factor_rows": int(len(factor_rows)),
                    "marker_defs": int(len(marker_defs)),
                    "pen_points": int(len(points)),
                    "polyline_defs": int(len(polyline_defs)),
                    "db_changes": int(wrote),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
