from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..factor.slices_service import FactorSlicesService
from ..factor.store import FactorStore
from ..overlay.package_builder_v1 import OverlayReplayBuildParamsV1, build_overlay_replay_package_v1
from ..overlay.store import OverlayStore
from ..storage.candle_store import CandleStore
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds
from .package_protocol_v1 import (
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayKlineBarV1,
    ReplayPackageMetadataV1,
)


@dataclass(frozen=True)
class ReplayBuildParamsV1:
    series_id: str
    to_candle_time: int
    window_candles: int = 2000
    window_size: int = 500
    snapshot_interval: int = 25
    preload_offset: int = 0


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_replay_package_v1(
    *,
    package_path: Path,
    cache_key: str,
    candle_store: CandleStore,
    factor_store: FactorStore,
    overlay_store: OverlayStore,
    factor_slices_service: FactorSlicesService,
    params: ReplayBuildParamsV1,
) -> None:
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
        ReplayKlineBarV1(
            time=int(candle.candle_time),
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=float(candle.volume),
        )
        for candle in candles
    ]
    if kline_all:
        kline_all.sort(key=lambda row: int(row.time))
    if not kline_all:
        raise ValueError("no_candles")

    from_time = int(kline_all[0].time)
    to_time = int(kline_all[-1].time)
    overlay_pkg = build_overlay_replay_package_v1(
        candle_store=candle_store,
        overlay_store=overlay_store,
        params=OverlayReplayBuildParamsV1(
            series_id=params.series_id,
            to_candle_time=int(to_time),
            window_candles=int(window_candles),
            window_size=int(window_size),
            snapshot_interval=int(snapshot_interval),
            preload_offset=int(params.preload_offset),
        ),
    )

    events = factor_store.get_events_between_times(
        series_id=params.series_id,
        factor_name=None,
        start_candle_time=int(from_time),
        end_candle_time=int(to_time),
        limit=200000,
    )
    history_events = [
        ReplayHistoryEventV1(
            event_id=int(event.id),
            factor_name=str(event.factor_name),
            candle_time=int(event.candle_time),
            kind=str(event.kind),
            event_key=str(event.event_key),
            payload=dict(event.payload or {}),
        )
        for event in events
    ]

    history_deltas: list[ReplayHistoryDeltaV1] = []
    events_sorted = sorted(events, key=lambda row: (int(row.candle_time), int(row.id)))
    last_event_id = 0
    event_idx = 0
    for idx, bar in enumerate(kline_all):
        prev_event_id = int(last_event_id)
        while event_idx < len(events_sorted) and int(events_sorted[event_idx].candle_time) <= int(bar.time):
            last_event_id = int(events_sorted[event_idx].id)
            event_idx += 1
        history_deltas.append(
            ReplayHistoryDeltaV1(
                idx=int(idx),
                from_event_id=int(prev_event_id),
                to_event_id=int(last_event_id),
            )
        )

    head_snapshots: list[ReplayFactorHeadSnapshotV1] = []
    for bar in kline_all:
        slices = factor_slices_service.get_slices(
            series_id=params.series_id,
            at_time=int(bar.time),
            window_candles=int(window_candles),
        )
        for factor_name, snapshot in (slices.snapshots or {}).items():
            head_snapshots.append(
                ReplayFactorHeadSnapshotV1(
                    factor_name=str(factor_name),
                    candle_time=int(bar.time),
                    seq=0,
                    head=dict(snapshot.head or {}),
                )
            )

    metadata = ReplayPackageMetadataV1(
        schema_version=1,
        series_id=params.series_id,
        timeframe_s=int(tf_s),
        total_candles=int(len(kline_all)),
        from_candle_time=int(from_time),
        to_candle_time=int(to_time),
        window_size=int(window_size),
        snapshot_interval=int(snapshot_interval),
        preload_offset=int(params.preload_offset),
        idx_to_time="windows[*].kline[idx].time",
    )
    payload = {
        "schema_version": 1,
        "cache_key": str(cache_key),
        "metadata": metadata.model_dump(mode="json"),
        "windows": [window.model_dump(mode="json") for window in overlay_pkg.windows],
        "history_events": [row.model_dump(mode="json") for row in history_events],
        "history_deltas": [row.model_dump(mode="json") for row in history_deltas],
        "factor_head_snapshots": [row.model_dump(mode="json") for row in head_snapshots],
        "candle_store_head_time": int(candle_store.head_time(params.series_id) or 0),
        "factor_store_last_event_id": int(factor_store.last_event_id(params.series_id)),
        "overlay_store_last_version_id": int(overlay_store.last_version_id(params.series_id)),
        "created_at_ms": int(time.time() * 1000),
    }

    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
