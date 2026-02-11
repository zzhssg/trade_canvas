from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..overlay_integrity_plugins import evaluate_overlay_integrity
from ..overlay_store import OverlayInstructionVersionRow
from ..schemas import DrawCursorV1, DrawDeltaV1, GetFactorSlicesResponseV1, OverlayInstructionPatchItemV1
from ..service_errors import ServiceError
from ..timeframe import series_id_timeframe, timeframe_to_seconds


class _StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class _OverlayStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def get_latest_defs_up_to_time(self, *, series_id: str, up_to_time: int) -> list[OverlayInstructionVersionRow]: ...

    def get_patch_after_version(
        self,
        *,
        series_id: str,
        after_version_id: int,
        up_to_time: int,
        limit: int = 50000,
    ) -> list[OverlayInstructionVersionRow]: ...

    def last_version_id(self, series_id: str) -> int: ...


class _OverlayOrchestratorLike(Protocol):
    def reset_series(self, *, series_id: str) -> None: ...

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...


class _FactorReadServiceLike(Protocol):
    strict_mode: bool

    def read_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
    ) -> GetFactorSlicesResponseV1: ...


class _DebugHubLike(Protocol):
    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class DrawReadService:
    store: _StoreLike
    overlay_store: _OverlayStoreLike
    overlay_orchestrator: _OverlayOrchestratorLike
    factor_read_service: _FactorReadServiceLike
    debug_hub: _DebugHubLike
    debug_api_enabled: bool = False

    def _empty_delta(self, *, series_id: str, cursor_version_id: int) -> DrawDeltaV1:
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=None,
            to_candle_time=None,
            active_ids=[],
            instruction_catalog_patch=[],
            series_points={},
            next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
        )

    def _debug_enabled(self) -> bool:
        return bool(self.debug_api_enabled)

    def read_delta(
        self,
        *,
        series_id: str,
        cursor_version_id: int,
        window_candles: int,
        at_time: int | None,
    ) -> DrawDeltaV1:
        strict_mode = bool(getattr(self.factor_read_service, "strict_mode", False))
        store_head = self.store.head_time(series_id)
        overlay_head = self.overlay_store.head_time(series_id)

        if at_time is not None:
            aligned = self.store.floor_time(series_id, at_time=int(at_time))
            if aligned is None:
                return self._empty_delta(series_id=series_id, cursor_version_id=int(cursor_version_id))
            if overlay_head is None or int(overlay_head) < int(aligned):
                raise ServiceError(
                    status_code=409,
                    detail="ledger_out_of_sync:overlay",
                    code="draw_read.ledger_out_of_sync.overlay",
                )
            to_time = int(aligned)
        else:
            to_time = store_head if store_head is not None else overlay_head
        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        if strict_mode and to_time is not None:
            if overlay_head is None or int(overlay_head) < int(to_time):
                raise ServiceError(
                    status_code=409,
                    detail="ledger_out_of_sync:overlay",
                    code="draw_read.ledger_out_of_sync.overlay",
                )

        if to_time is None:
            return self._empty_delta(series_id=series_id, cursor_version_id=int(cursor_version_id))

        slices_for_overlay = None
        if int(cursor_version_id) == 0:
            if self.factor_read_service is None:
                raise ServiceError(
                    status_code=500,
                    detail="factor_read_service_not_ready",
                    code="draw_read.factor_service_not_ready",
                )
            slices_for_overlay = self.factor_read_service.read_slices(
                series_id=series_id,
                at_time=int(to_time),
                aligned_time=int(to_time),
                window_candles=int(window_candles),
                ensure_fresh=True,
            )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = self.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        if int(cursor_version_id) == 0:
            slices = slices_for_overlay
            if slices is None:
                slices = GetFactorSlicesResponseV1(
                    series_id=series_id,
                    at_time=int(to_time),
                    candle_id=f"{series_id}:{int(to_time)}",
                )
            should_rebuild_overlay, integrity_results = evaluate_overlay_integrity(
                series_id=series_id,
                slices=slices,
                latest_defs=latest_defs,
            )
            if should_rebuild_overlay:
                if strict_mode:
                    raise ServiceError(
                        status_code=409,
                        detail="ledger_out_of_sync:overlay",
                        code="draw_read.ledger_out_of_sync.overlay",
                    )
                self.overlay_orchestrator.reset_series(series_id=series_id)
                self.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_time))
                latest_defs = self.overlay_store.get_latest_defs_up_to_time(
                    series_id=series_id,
                    up_to_time=int(to_time),
                )
                if self._debug_enabled():
                    self.debug_hub.emit(
                        pipe="read",
                        event="read.http.draw_delta.overlay_rebuild",
                        series_id=series_id,
                        message="overlay rebuilt by integrity plugins",
                        data={
                            "at_time": int(to_time),
                            "checks": [
                                {
                                    "plugin": str(item.plugin_name),
                                    "should_rebuild": bool(item.should_rebuild),
                                    "reason": None if item.reason is None else str(item.reason),
                                }
                                for item in integrity_results
                            ],
                        },
                    )

        active_ids: list[str] = []
        for definition in latest_defs:
            if definition.kind == "marker":
                marker_time = definition.payload.get("time")
                try:
                    pivot_time = int(marker_time)
                except Exception:
                    continue
                if pivot_time < cutoff_time or pivot_time > int(to_time):
                    continue
                active_ids.append(str(definition.instruction_id))
            elif definition.kind == "polyline":
                points = definition.payload.get("points")
                if not isinstance(points, list) or not points:
                    continue
                has_visible_point = False
                for point in points:
                    if not isinstance(point, dict):
                        continue
                    point_time = point.get("time")
                    if point_time is None:
                        continue
                    try:
                        point_time_int = int(point_time)
                    except Exception:
                        continue
                    if cutoff_time <= point_time_int <= int(to_time):
                        has_visible_point = True
                        break
                if has_visible_point:
                    active_ids.append(str(definition.instruction_id))

        patch_rows = self.overlay_store.get_patch_after_version(
            series_id=series_id,
            after_version_id=int(cursor_version_id),
            up_to_time=int(to_time),
        )
        patch = [
            OverlayInstructionPatchItemV1(
                version_id=row.version_id,
                instruction_id=row.instruction_id,
                kind=row.kind,
                visible_time=row.visible_time,
                definition=row.payload,
            )
            for row in patch_rows
        ]
        next_cursor = DrawCursorV1(version_id=int(self.overlay_store.last_version_id(series_id)), point_time=None)

        active_ids.sort()
        if self._debug_enabled() and (patch or int(next_cursor.version_id) > int(cursor_version_id)):
            self.debug_hub.emit(
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
