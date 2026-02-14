from __future__ import annotations

from dataclasses import dataclass

from ..core.ports import AlignedStorePort, DebugHubPort
from ..overlay.integrity_plugins import evaluate_overlay_integrity
from ..overlay.store import OverlayInstructionVersionRow
from ..core.schemas import GetFactorSlicesResponseV1, OverlayInstructionPatchItemV1
from ..core.service_errors import ServiceError
from .ports import FactorReadServicePort, OverlayStoreReadPort

@dataclass(frozen=True)
class DrawDeltaDebugEmitRequest:
    debug_enabled: bool
    debug_hub: DebugHubPort
    series_id: str
    cursor_version_id: int
    next_version_id: int
    to_time: int
    patch_len: int
    active_len: int
    at_time: int | None


def overlay_out_of_sync_error() -> ServiceError:
    return ServiceError(
        status_code=409,
        detail="ledger_out_of_sync:overlay",
        code="draw_read.ledger_out_of_sync.overlay",
    )


def assert_overlay_head_covers(*, required_time: int, overlay_head: int | None) -> None:
    if overlay_head is None or int(overlay_head) < int(required_time):
        raise overlay_out_of_sync_error()


def resolve_to_time(
    *,
    store: AlignedStorePort,
    series_id: str,
    at_time: int | None,
    store_head: int | None,
    overlay_head: int | None,
) -> int | None:
    if at_time is not None:
        aligned = store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            return None
        aligned_time = int(aligned)
        assert_overlay_head_covers(
            required_time=aligned_time,
            overlay_head=overlay_head,
        )
        return aligned_time

    if store_head is not None:
        return int(store_head)
    if overlay_head is not None:
        return int(overlay_head)
    return None


def read_slices_for_overlay_if_needed(
    *,
    factor_read_service: FactorReadServicePort | None,
    series_id: str,
    cursor_version_id: int,
    window_candles: int,
    to_time: int,
) -> GetFactorSlicesResponseV1 | None:
    if int(cursor_version_id) != 0:
        return None
    if factor_read_service is None:
        raise ServiceError(
            status_code=500,
            detail="factor_read_service_not_ready",
            code="draw_read.factor_service_not_ready",
        )
    return factor_read_service.read_slices(
        series_id=series_id,
        at_time=int(to_time),
        aligned_time=int(to_time),
        window_candles=int(window_candles),
        ensure_fresh=True,
    )


def ensure_overlay_integrity_if_needed(
    *,
    series_id: str,
    cursor_version_id: int,
    to_time: int,
    strict_mode: bool,
    latest_defs: list[OverlayInstructionVersionRow],
    slices_for_overlay: GetFactorSlicesResponseV1 | None,
    debug_enabled: bool,
    debug_hub: DebugHubPort,
) -> None:
    if int(cursor_version_id) != 0:
        return

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
    if not should_rebuild_overlay:
        return
    if bool(debug_enabled):
        debug_hub.emit(
            pipe="read",
            event="read.http.draw_delta.overlay_out_of_sync",
            series_id=series_id,
            message="overlay integrity check failed; explicit repair required",
            data={
                "at_time": int(to_time),
                "strict_mode": bool(strict_mode),
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
    raise overlay_out_of_sync_error()


def collect_active_ids(
    *,
    latest_defs: list[OverlayInstructionVersionRow],
    cutoff_time: int,
    to_time: int,
) -> list[str]:
    active_ids: list[str] = []
    for definition in latest_defs:
        if definition.kind == "marker":
            marker_time = definition.payload.get("time")
            if marker_time is None:
                continue
            try:
                pivot_time = int(marker_time)
            except (ValueError, TypeError):
                continue
            if pivot_time < int(cutoff_time) or pivot_time > int(to_time):
                continue
            active_ids.append(str(definition.instruction_id))
            continue

        if definition.kind != "polyline":
            continue
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
            except (ValueError, TypeError):
                continue
            if int(cutoff_time) <= point_time_int <= int(to_time):
                has_visible_point = True
                break
        if has_visible_point:
            active_ids.append(str(definition.instruction_id))
    active_ids.sort()
    return active_ids


def build_patch(
    *,
    overlay_store: OverlayStoreReadPort,
    series_id: str,
    cursor_version_id: int,
    to_time: int,
) -> list[OverlayInstructionPatchItemV1]:
    patch_rows = overlay_store.get_patch_after_version(
        series_id=series_id,
        after_version_id=int(cursor_version_id),
        up_to_time=int(to_time),
    )
    return [
        OverlayInstructionPatchItemV1(
            version_id=row.version_id,
            instruction_id=row.instruction_id,
            kind=row.kind,
            visible_time=row.visible_time,
            definition=row.payload,
        )
        for row in patch_rows
    ]


def emit_draw_delta_debug_if_needed(request: DrawDeltaDebugEmitRequest) -> None:
    if not bool(request.debug_enabled):
        return
    if int(request.patch_len) <= 0 and int(request.next_version_id) <= int(request.cursor_version_id):
        return
    request.debug_hub.emit(
        pipe="read",
        event="read.http.draw_delta",
        series_id=request.series_id,
        message="get draw delta",
        data={
            "cursor_version_id": int(request.cursor_version_id),
            "next_version_id": int(request.next_version_id),
            "to_time": int(request.to_time),
            "patch_len": int(request.patch_len),
            "active_len": int(request.active_len),
            "at_time": None if request.at_time is None else int(request.at_time),
        },
    )
