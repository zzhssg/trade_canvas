from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ..factor.manifest import build_default_factor_manifest
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
    ReplayFactorSchemaV1,
    ReplayFactorSnapshotV1,
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
    factor_snapshots: list[ReplayFactorSnapshotV1] = []
    factor_schema_state: dict[str, dict[str, set[str]]] = {}
    last_snapshot_sig_by_factor: dict[str, str] = {}
    for bar in kline_all:
        slices = factor_slices_service.get_slices(
            series_id=params.series_id,
            at_time=int(bar.time),
            window_candles=int(window_candles),
        )
        for factor_name, snapshot in (slices.snapshots or {}).items():
            factor_key = str(factor_name)
            snapshot_payload = snapshot.model_dump(mode="json")
            history_obj = snapshot_payload.get("history")
            head_obj = snapshot_payload.get("head")
            history_keys = set(history_obj.keys()) if isinstance(history_obj, dict) else set()
            head_keys = set(head_obj.keys()) if isinstance(head_obj, dict) else set()
            schema_state = factor_schema_state.setdefault(
                factor_key,
                {"history": set(), "head": set()},
            )
            schema_state["history"].update(str(key) for key in history_keys)
            schema_state["head"].update(str(key) for key in head_keys)

            snapshot_sig = stable_json_dumps(snapshot_payload)
            if last_snapshot_sig_by_factor.get(factor_key) != snapshot_sig:
                factor_snapshots.append(
                    ReplayFactorSnapshotV1(
                        factor_name=factor_key,
                        candle_time=int(bar.time),
                        snapshot=snapshot,
                    )
                )
                last_snapshot_sig_by_factor[factor_key] = snapshot_sig

    default_factor_manifest = build_default_factor_manifest()
    for spec in default_factor_manifest.specs():
        factor_schema_state.setdefault(
            str(spec.factor_name),
            {"history": set(), "head": set()},
        )

    factor_schema = [
        ReplayFactorSchemaV1(
            factor_name=factor_name,
            history_keys=sorted(schema_state["history"]),
            head_keys=sorted(schema_state["head"]),
        )
        for factor_name, schema_state in sorted(factor_schema_state.items(), key=lambda item: str(item[0]))
    ]

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
        factor_schema=factor_schema,
    )
    payload = {
        "schema_version": 1,
        "cache_key": str(cache_key),
        "metadata": metadata.model_dump(mode="json"),
        "windows": [window.model_dump(mode="json") for window in overlay_pkg.windows],
        "factor_snapshots": [row.model_dump(mode="json") for row in factor_snapshots],
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
