from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ..factor.slices_service import FactorSlicesService
from ..factor.store import FactorStore
from ..overlay.package_builder_v1 import (
    OverlayReplayBuildParamsV1,
    build_overlay_replay_package_v1,
    stable_json_dumps,
)
from ..overlay.store import OverlayStore
from ..storage.candle_store import CandleStore
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
    window_candles = max(1, int(params.window_candles))
    overlay_pkg = build_overlay_replay_package_v1(
        candle_store=candle_store,
        overlay_store=overlay_store,
        params=OverlayReplayBuildParamsV1(
            series_id=params.series_id,
            to_candle_time=int(params.to_candle_time),
            window_candles=int(params.window_candles),
            window_size=int(params.window_size),
            snapshot_interval=int(params.snapshot_interval),
            preload_offset=int(params.preload_offset),
        ),
    )
    if int(overlay_pkg.metadata.total_candles) <= 0:
        raise ValueError("no_candles")
    kline_all = [
        ReplayKlineBarV1(
            time=int(bar.time),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
        )
        for window in overlay_pkg.windows
        for bar in window.kline
    ]
    from_time = int(overlay_pkg.metadata.from_candle_time)
    to_time = int(overlay_pkg.metadata.to_candle_time)

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
        timeframe_s=int(overlay_pkg.metadata.timeframe_s),
        total_candles=int(overlay_pkg.metadata.total_candles),
        from_candle_time=int(overlay_pkg.metadata.from_candle_time),
        to_candle_time=int(overlay_pkg.metadata.to_candle_time),
        window_size=int(overlay_pkg.metadata.window_size),
        snapshot_interval=int(overlay_pkg.metadata.snapshot_interval),
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
