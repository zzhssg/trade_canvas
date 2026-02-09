from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .factor_read_freshness import read_factor_slices_with_freshness
from .schemas import DrawCursorV1, DrawDeltaV1, LimitQuery, OverlayInstructionPatchItemV1
from .timeframe import series_id_timeframe, timeframe_to_seconds

router = APIRouter()


def _compute_draw_delta(
    *,
    app: FastAPI,
    series_id: str,
    cursor_version_id: int,
    window_candles: int,
    at_time: int | None,
) -> DrawDeltaV1:
    store = app.state.store
    store_head = store.head_time(series_id)
    overlay_head = app.state.overlay_store.head_time(series_id)

    if at_time is not None:
        aligned = store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            return DrawDeltaV1(
                series_id=series_id,
                to_candle_id=None,
                to_candle_time=None,
                active_ids=[],
                instruction_catalog_patch=[],
                series_points={},
                next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
            )
        if overlay_head is None or int(overlay_head) < int(aligned):
            raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")
        to_time = int(aligned)
    else:
        to_time = store_head if store_head is not None else overlay_head
    to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

    if to_time is None:
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=None,
            to_candle_time=None,
            active_ids=[],
            instruction_catalog_patch=[],
            series_points={},
            next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
        )

    slices_for_overlay = None
    if int(cursor_version_id) == 0:
        slices_for_overlay = read_factor_slices_with_freshness(
            store=store,
            factor_orchestrator=app.state.factor_orchestrator,
            factor_slices_service=app.state.factor_slices_service,
            series_id=series_id,
            at_time=int(to_time),
            aligned_time=int(to_time),
            window_candles=int(window_candles),
        )

    tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

    latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
    if int(cursor_version_id) == 0:
        expected_start = 0
        expected_has_zhongshu = False
        expected_zhongshu_ids: set[str] = set()
        try:
            slices = slices_for_overlay
            if slices is None:
                raise RuntimeError("slices_not_ready")
            anchor_snapshot = (slices.snapshots or {}).get("anchor")
            anchor_head = (anchor_snapshot.head if anchor_snapshot is not None else {}) or {}
            current_ref = anchor_head.get("current_anchor_ref") if isinstance(anchor_head, dict) else None
            if isinstance(current_ref, dict):
                expected_start = int(current_ref.get("start_time") or 0)
            zhongshu_snapshot = (slices.snapshots or {}).get("zhongshu")
            if zhongshu_snapshot is not None:
                zhongshu_history = (zhongshu_snapshot.history or {}) if isinstance(zhongshu_snapshot.history, dict) else {}
                zhongshu_head = (zhongshu_snapshot.head or {}) if isinstance(zhongshu_snapshot.head, dict) else {}
                dead_items = zhongshu_history.get("dead")
                alive_items = zhongshu_head.get("alive")
                if isinstance(dead_items, list):
                    for item in dead_items:
                        if not isinstance(item, dict):
                            continue
                        try:
                            start_time = int(item.get("start_time") or 0)
                            end_time = int(item.get("end_time") or 0)
                            zg = float(item.get("zg") or 0.0)
                            zd = float(item.get("zd") or 0.0)
                        except Exception:
                            continue
                        if start_time <= 0 or end_time <= 0:
                            continue
                        base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
                        expected_zhongshu_ids.add(f"{base_id}:top")
                        expected_zhongshu_ids.add(f"{base_id}:bottom")
                if isinstance(alive_items, list) and alive_items:
                    expected_zhongshu_ids.add("zhongshu.alive:top")
                    expected_zhongshu_ids.add("zhongshu.alive:bottom")
                expected_has_zhongshu = bool(
                    (isinstance(dead_items, list) and len(dead_items) > 0)
                    or (isinstance(alive_items, list) and len(alive_items) > 0)
                )
        except Exception:
            expected_start = 0
            expected_has_zhongshu = False
            expected_zhongshu_ids = set()

        should_rebuild_overlay = False
        if expected_start > 0:
            current_def = next((d for d in latest_defs if d.kind == "polyline" and d.instruction_id == "anchor.current"), None)
            rendered_start = 0
            if current_def is not None:
                pts = current_def.payload.get("points")
                if isinstance(pts, list) and pts:
                    first = pts[0]
                    if isinstance(first, dict):
                        try:
                            rendered_start = int(first.get("time") or 0)
                        except Exception:
                            rendered_start = 0
            if int(rendered_start) != int(expected_start):
                should_rebuild_overlay = True

        rendered_has_zhongshu = any(str(d.instruction_id).startswith("zhongshu.") for d in latest_defs)
        if bool(rendered_has_zhongshu) != bool(expected_has_zhongshu):
            should_rebuild_overlay = True
        rendered_zhongshu_ids = {str(d.instruction_id) for d in latest_defs if str(d.instruction_id).startswith("zhongshu.")}
        if rendered_zhongshu_ids != expected_zhongshu_ids:
            should_rebuild_overlay = True

        if should_rebuild_overlay:
            app.state.overlay_orchestrator.reset_series(series_id=series_id)
            app.state.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_time))
            latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(
                series_id=series_id, up_to_time=int(to_time)
            )
    active_ids: list[str] = []
    for d in latest_defs:
        if d.kind == "marker":
            t = d.payload.get("time")
            try:
                pivot_time = int(t)
            except Exception:
                continue
            if pivot_time < cutoff_time or pivot_time > int(to_time):
                continue
            active_ids.append(str(d.instruction_id))
        elif d.kind == "polyline":
            pts = d.payload.get("points")
            if not isinstance(pts, list) or not pts:
                continue
            ok = False
            for p in pts:
                if not isinstance(p, dict):
                    continue
                tt = p.get("time")
                if tt is None:
                    continue
                try:
                    pt = int(tt)
                except Exception:
                    continue
                if cutoff_time <= pt <= int(to_time):
                    ok = True
                    break
            if ok:
                active_ids.append(str(d.instruction_id))

    patch_rows = app.state.overlay_store.get_patch_after_version(
        series_id=series_id,
        after_version_id=int(cursor_version_id),
        up_to_time=int(to_time),
    )
    patch = [
        OverlayInstructionPatchItemV1(
            version_id=r.version_id,
            instruction_id=r.instruction_id,
            kind=r.kind,
            visible_time=r.visible_time,
            definition=r.payload,
        )
        for r in patch_rows
    ]
    next_cursor = DrawCursorV1(version_id=int(app.state.overlay_store.last_version_id(series_id)), point_time=None)

    active_ids.sort()
    if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1" and (patch or int(next_cursor.version_id) > int(cursor_version_id)):
        app.state.debug_hub.emit(
            pipe="read",
            event="read.http.draw_delta",
            series_id=series_id,
            message="get draw delta",
            data={
                "cursor_version_id": int(cursor_version_id),
                "next_version_id": int(next_cursor.version_id),
                "to_time": None if to_time is None else int(to_time),
                "patch_len": int(len(patch)),
                "active_len": int(len(active_ids)),
                "at_time": None if at_time is None else int(at_time),
            },
        )
    return DrawDeltaV1(
        series_id=series_id,
        to_candle_id=to_candle_id,
        to_candle_time=int(to_time),
        active_ids=active_ids,
        instruction_catalog_patch=patch,
        series_points={},
        next_cursor=next_cursor,
    )


@router.get("/api/draw/delta", response_model=DrawDeltaV1)
def get_draw_delta(
    request: Request,
    series_id: str = Query(..., min_length=1),
    cursor_version_id: int = Query(0, ge=0),
    window_candles: LimitQuery = 2000,
    at_time: int | None = Query(default=None, ge=0, description="Optional replay upper-bound (Unix seconds)"),
) -> DrawDeltaV1:
    return _compute_draw_delta(
        app=request.app,
        series_id=series_id,
        cursor_version_id=int(cursor_version_id),
        window_candles=int(window_candles),
        at_time=None if at_time is None else int(at_time),
    )


def register_draw_routes(app: FastAPI) -> None:
    app.include_router(router)

    def _read_draw_delta(*, series_id: str, cursor_version_id: int, window_candles: int, at_time: int | None) -> DrawDeltaV1:
        return _compute_draw_delta(
            app=app,
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            window_candles=int(window_candles),
            at_time=None if at_time is None else int(at_time),
        )

    app.state.read_draw_delta = _read_draw_delta
