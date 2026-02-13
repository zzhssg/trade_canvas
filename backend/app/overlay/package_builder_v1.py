from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..schemas import OverlayInstructionPatchItemV1
from ..store import CandleStore
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from .replay_protocol_v1 import (
    OverlayReplayCheckpointV1,
    OverlayReplayDeltaMetaV1,
    OverlayReplayDeltaPackageV1,
    OverlayReplayDiffV1,
    OverlayReplayKlineBarV1,
    OverlayReplayPackageMetadataV1,
    OverlayReplayWindowMetaV1,
    OverlayReplayWindowV1,
)
from .store import OverlayInstructionVersionRow, OverlayStore


@dataclass(frozen=True)
class OverlayReplayBuildParamsV1:
    series_id: str
    to_candle_time: int
    window_candles: int = 2000
    window_size: int = 500
    snapshot_interval: int = 25
    preload_offset: int = 0


def _overlay_item_from_row(r: OverlayInstructionVersionRow) -> OverlayInstructionPatchItemV1:
    return OverlayInstructionPatchItemV1(
        version_id=int(r.version_id),
        instruction_id=str(r.instruction_id),
        kind=str(r.kind),
        visible_time=int(r.visible_time),
        definition=dict(r.payload or {}),
    )


def _marker_time(defn: dict[str, Any]) -> int | None:
    t = defn.get("time")
    if t is None:
        return None
    try:
        tt = int(t)
    except Exception:
        return None
    return tt if tt >= 0 else None


def _polyline_min_max(defn: dict[str, Any]) -> tuple[int | None, int | None]:
    pts = defn.get("points")
    if not isinstance(pts, list) or not pts:
        return (None, None)
    mn: int | None = None
    mx: int | None = None
    for p in pts:
        if not isinstance(p, dict):
            continue
        t = p.get("time")
        if t is None:
            continue
        try:
            tt = int(t)
        except Exception:
            continue
        if tt < 0:
            continue
        mn = tt if mn is None else min(mn, tt)
        mx = tt if mx is None else max(mx, tt)
    return (mn, mx)


def _is_relevant_for_range(item: OverlayInstructionPatchItemV1, *, cutoff_time: int, to_time: int) -> bool:
    d = item.definition if isinstance(item.definition, dict) else {}
    if item.kind == "marker":
        t = _marker_time(d)
        if t is None:
            return False
        return int(cutoff_time) <= int(t) <= int(to_time)
    if item.kind == "polyline":
        mn, mx = _polyline_min_max(d)
        if mn is None or mx is None:
            return False
        return int(mx) >= int(cutoff_time) and int(mn) <= int(to_time)
    return True


def compute_active_ids_v1(
    catalog: dict[str, OverlayInstructionPatchItemV1],
    *,
    cutoff_time: int,
    to_time: int,
) -> list[str]:
    out: list[str] = []
    for iid, item in catalog.items():
        d = item.definition if isinstance(item.definition, dict) else {}
        if item.kind == "marker":
            t = _marker_time(d)
            if t is None:
                continue
            if int(cutoff_time) <= int(t) <= int(to_time):
                out.append(iid)
            continue
        if item.kind == "polyline":
            mn, mx = _polyline_min_max(d)
            if mn is None or mx is None:
                continue
            if int(mx) < int(cutoff_time):
                continue
            if int(mn) <= int(to_time):
                out.append(iid)
            continue
        out.append(iid)
    out.sort()
    return out


def build_overlay_replay_package_v1(
    *,
    candle_store: CandleStore,
    overlay_store: OverlayStore,
    params: OverlayReplayBuildParamsV1,
) -> OverlayReplayDeltaPackageV1:
    tf_s = timeframe_to_seconds(series_id_timeframe(params.series_id))
    window_candles = max(1, int(params.window_candles))
    window_size = max(1, int(params.window_size))
    snapshot_interval = max(1, int(params.snapshot_interval))

    end_time = int(params.to_candle_time)
    start_time = max(0, end_time - (window_candles - 1) * int(tf_s))

    candles = candle_store.get_closed_between_times(
        params.series_id,
        start_time=int(start_time),
        end_time=int(end_time),
        limit=int(window_candles) + 10,
    )
    kline_all = [
        OverlayReplayKlineBarV1(
            time=int(c.candle_time),
            open=float(c.open),
            high=float(c.high),
            low=float(c.low),
            close=float(c.close),
            volume=float(c.volume),
        )
        for c in candles
    ]
    if kline_all:
        # Ensure determinism: enforce ascending by time.
        kline_all.sort(key=lambda b: int(b.time))

    total = len(kline_all)
    from_time = int(kline_all[0].time) if total else int(start_time)
    to_time = int(kline_all[-1].time) if total else int(end_time)

    overlay_last_version_id = int(overlay_store.last_version_id(params.series_id))

    windows: list[OverlayReplayWindowV1] = []
    window_metas: list[OverlayReplayWindowMetaV1] = []

    for w in range(0, total, window_size):
        start_idx = int(w)
        end_idx = int(min(total, w + window_size))
        if start_idx >= end_idx:
            continue
        window_index = int(start_idx // window_size)
        window_kline = kline_all[start_idx:end_idx]
        window_start_time = int(window_kline[0].time)
        window_end_time = int(window_kline[-1].time)

        # Catalog base @ window start (latest defs up to the window start time).
        base_rows = overlay_store.get_latest_defs_up_to_time(
            series_id=params.series_id,
            up_to_time=int(window_start_time),
        )
        base_items_all = [_overlay_item_from_row(r) for r in base_rows]
        base_items = [
            it
            for it in base_items_all
            if _is_relevant_for_range(it, cutoff_time=int(from_time), to_time=int(to_time))
        ]
        base_items.sort(key=lambda it: (int(it.visible_time), int(it.version_id), str(it.instruction_id)))

        # Catalog patch within this window: visible_time in (window_start_time, window_end_time].
        patch_rows = overlay_store.get_versions_between_times(
            series_id=params.series_id,
            start_visible_time=int(window_start_time) + 1,
            end_visible_time=int(window_end_time),
            limit=200000,
        )
        patch_items_all = [_overlay_item_from_row(r) for r in patch_rows]
        patch_items = [
            it
            for it in patch_items_all
            if _is_relevant_for_range(it, cutoff_time=int(from_time), to_time=int(to_time))
        ]
        patch_items.sort(key=lambda it: (int(it.visible_time), int(it.version_id), str(it.instruction_id)))

        # Rebuild active_ids via checkpoint + diff (window-independent).
        catalog: dict[str, OverlayInstructionPatchItemV1] = {it.instruction_id: it for it in base_items}

        patch_cursor = 0
        checkpoints: list[OverlayReplayCheckpointV1] = []
        diffs: list[OverlayReplayDiffV1] = []

        prev_active: set[str] | None = None
        for idx in range(start_idx, end_idx):
            cur_time = int(kline_all[idx].time)

            # Apply catalog patch items whose visible_time <= cur_time.
            while patch_cursor < len(patch_items) and int(patch_items[patch_cursor].visible_time) <= int(cur_time):
                it = patch_items[patch_cursor]
                catalog[it.instruction_id] = it
                patch_cursor += 1

            active = compute_active_ids_v1(catalog, cutoff_time=int(from_time), to_time=int(cur_time))
            active_set = set(active)

            # Always include a checkpoint at window start for window-independent reconstruction.
            if idx == start_idx or (idx - start_idx) % snapshot_interval == 0:
                checkpoints.append(OverlayReplayCheckpointV1(at_idx=int(idx), active_ids=active))

            if prev_active is None:
                prev_active = active_set
                continue

            add_ids = sorted(active_set - prev_active)
            remove_ids = sorted(prev_active - active_set)
            if add_ids or remove_ids:
                diffs.append(OverlayReplayDiffV1(at_idx=int(idx), add_ids=add_ids, remove_ids=remove_ids))
            prev_active = active_set

        windows.append(
            OverlayReplayWindowV1(
                window_index=window_index,
                start_idx=start_idx,
                end_idx=end_idx,
                kline=window_kline,
                catalog_base=base_items,
                catalog_patch=patch_items,
                checkpoints=checkpoints,
                diffs=diffs,
                event_catalog=None,
            )
        )
        window_metas.append(
            OverlayReplayWindowMetaV1(
                window_index=window_index,
                start_idx=start_idx,
                end_idx=end_idx,
                start_time=window_start_time,
                end_time=window_end_time,
            )
        )

    meta = OverlayReplayDeltaMetaV1(
        series_id=params.series_id,
        to_candle_time=int(to_time),
        from_candle_time=int(from_time),
        total_candles=int(total),
        window_size=int(window_size),
        snapshot_interval=int(snapshot_interval),
        windows=window_metas,
        overlay_store_last_version_id=int(overlay_last_version_id),
    )
    pkg_meta = OverlayReplayPackageMetadataV1(
        series_id=params.series_id,
        timeframe_s=int(tf_s),
        total_candles=int(total),
        from_candle_time=int(from_time),
        to_candle_time=int(to_time),
        window_size=int(window_size),
        snapshot_interval=int(snapshot_interval),
        preload_offset=int(params.preload_offset),
    )
    return OverlayReplayDeltaPackageV1(metadata=pkg_meta, delta_meta=meta, windows=windows)


def stable_json_dumps(obj: Any) -> str:
    """
    Stable json serialization used by cache-key hashing.
    """
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
