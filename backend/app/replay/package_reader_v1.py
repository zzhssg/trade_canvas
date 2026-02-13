from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..overlay.replay_protocol_v1 import OverlayReplayCheckpointV1, OverlayReplayDiffV1
from ..core.schemas import OverlayInstructionPatchItemV1
from ..core.service_errors import ServiceError
from ..storage.candle_store import CandleStore
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds
from .package_protocol_v1 import (
    ReplayCoverageV1,
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayKlineBarV1,
    ReplayPackageMetadataV1,
    ReplayWindowV1,
)


class ReplayPackageReaderV1:
    def __init__(self, *, candle_store: CandleStore, root_dir: Path) -> None:
        self._candle_store = candle_store
        self._root_dir = Path(root_dir)

    def cache_dir(self, cache_key: str) -> Path:
        return self._root_dir / str(cache_key)

    def package_path(self, cache_key: str) -> Path:
        return self.cache_dir(cache_key) / "replay_package.json"

    def cache_exists(self, cache_key: str) -> bool:
        return self.package_path(cache_key).exists()

    def resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        store_head = self._candle_store.head_time(series_id)
        if store_head is None and to_time is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay.no_data")
        requested = int(to_time) if to_time is not None else int(store_head or 0)
        aligned = self._candle_store.floor_time(series_id, at_time=int(requested))
        if aligned is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay.no_data")
        return int(aligned)

    def coverage(
        self,
        *,
        series_id: str,
        to_time: int,
        target_candles: int,
    ) -> ReplayCoverageV1:
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(to_time) - (int(target_candles) - 1) * int(tf_s))
        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(to_time),
            limit=int(target_candles),
        )
        from_time = int(candles[0].candle_time) if candles else None
        return ReplayCoverageV1(
            required_candles=int(target_candles),
            candles_ready=int(len(candles)),
            from_time=from_time,
            to_time=int(to_time),
        )

    def read_meta(self, cache_key: str) -> ReplayPackageMetadataV1:
        payload = self._read_package(cache_key)
        meta = payload.get("metadata")
        if not isinstance(meta, dict):
            raise RuntimeError("missing_replay_metadata")
        return ReplayPackageMetadataV1.model_validate(meta)

    def read_history_events(self, cache_key: str) -> list[ReplayHistoryEventV1]:
        payload = self._read_package(cache_key)
        events = payload.get("history_events")
        if not isinstance(events, list):
            return []
        out: list[ReplayHistoryEventV1] = []
        for raw in events:
            if isinstance(raw, dict):
                out.append(ReplayHistoryEventV1.model_validate(raw))
        return out

    def read_window(self, cache_key: str, *, target_idx: int) -> ReplayWindowV1:
        payload = self._read_package(cache_key)
        meta = self.read_meta(cache_key)
        total = int(meta.total_candles)
        idx = int(target_idx)
        if idx < 0 or idx >= total:
            raise ServiceError(
                status_code=422,
                detail="target_idx_out_of_range",
                code="replay.window.target_idx_out_of_range",
            )
        window_index = idx // int(meta.window_size)
        windows = payload.get("windows")
        if not isinstance(windows, list):
            raise ServiceError(status_code=404, detail="not_found", code="replay.window.not_found")
        raw_window = next(
            (
                item
                for item in windows
                if isinstance(item, dict) and int(item.get("window_index", -1)) == int(window_index)
            ),
            None,
        )
        if raw_window is None:
            raise ServiceError(status_code=404, detail="not_found", code="replay.window.not_found")

        return ReplayWindowV1(
            window_index=int(raw_window.get("window_index", 0)),
            start_idx=int(raw_window.get("start_idx", 0)),
            end_idx=int(raw_window.get("end_idx", 0)),
            kline=[
                ReplayKlineBarV1.model_validate(item)
                for item in (raw_window.get("kline") or [])
                if isinstance(item, dict)
            ],
            draw_catalog_base=[
                OverlayInstructionPatchItemV1.model_validate(item)
                for item in (raw_window.get("catalog_base") or [])
                if isinstance(item, dict)
            ],
            draw_catalog_patch=[
                OverlayInstructionPatchItemV1.model_validate(item)
                for item in (raw_window.get("catalog_patch") or [])
                if isinstance(item, dict)
            ],
            draw_active_checkpoints=[
                OverlayReplayCheckpointV1.model_validate(item)
                for item in (raw_window.get("checkpoints") or [])
                if isinstance(item, dict)
            ],
            draw_active_diffs=[
                OverlayReplayDiffV1.model_validate(item)
                for item in (raw_window.get("diffs") or [])
                if isinstance(item, dict)
            ],
        )

    def read_window_extras(
        self,
        *,
        cache_key: str,
        window: ReplayWindowV1,
    ) -> tuple[list[ReplayFactorHeadSnapshotV1], list[ReplayHistoryDeltaV1]]:
        payload = self._read_package(cache_key)
        head_rows_raw = payload.get("factor_head_snapshots")
        delta_rows_raw = payload.get("history_deltas")

        times = [int(bar.time) for bar in window.kline]
        min_time = int(times[0]) if times else None
        max_time = int(times[-1]) if times else None

        head_rows: list[ReplayFactorHeadSnapshotV1] = []
        if isinstance(head_rows_raw, list) and min_time is not None and max_time is not None:
            for raw in head_rows_raw:
                if not isinstance(raw, dict):
                    continue
                candle_time = int(raw.get("candle_time", -1))
                if candle_time < min_time or candle_time > max_time:
                    continue
                head_rows.append(ReplayFactorHeadSnapshotV1.model_validate(raw))

        deltas: list[ReplayHistoryDeltaV1] = []
        if isinstance(delta_rows_raw, list):
            start_idx = int(window.start_idx)
            end_idx = int(window.end_idx)
            for raw in delta_rows_raw:
                if not isinstance(raw, dict):
                    continue
                idx = int(raw.get("idx", -1))
                if start_idx <= idx < end_idx:
                    deltas.append(ReplayHistoryDeltaV1.model_validate(raw))
        return (head_rows, deltas)

    def read_preload_window(self, cache_key: str, meta: ReplayPackageMetadataV1) -> ReplayWindowV1 | None:
        if int(meta.total_candles) <= 0:
            return None
        target_idx = max(0, int(meta.total_candles) - 1 - int(meta.preload_offset))
        return self.read_window(cache_key, target_idx=int(target_idx))

    def _read_package(self, cache_key: str) -> dict[str, Any]:
        path = self.package_path(cache_key)
        if not path.exists():
            raise ServiceError(status_code=404, detail="not_found", code="replay.package.not_found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("replay_package_json_invalid") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("replay_package_json_invalid")
        return payload
