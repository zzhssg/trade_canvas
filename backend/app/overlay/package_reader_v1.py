from __future__ import annotations

import json
from pathlib import Path

from ..core.service_errors import ServiceError
from ..storage.candle_store import CandleStore
from .replay_protocol_v1 import (
    OverlayReplayDeltaMetaV1,
    OverlayReplayDeltaPackageV1,
    OverlayReplayWindowV1,
)
from .store import OverlayStore


class OverlayPackageReaderV1:
    def __init__(
        self,
        *,
        candle_store: CandleStore,
        overlay_store: OverlayStore,
        root_dir: Path,
    ) -> None:
        self._candle_store = candle_store
        self._overlay_store = overlay_store
        self._root_dir = Path(root_dir)

    def cache_dir(self, cache_key: str) -> Path:
        return self._root_dir / str(cache_key)

    def manifest_path(self, cache_key: str) -> Path:
        return self.cache_dir(cache_key) / "manifest.json"

    def meta_path(self, cache_key: str) -> Path:
        return self.cache_dir(cache_key) / "delta_meta.json"

    def package_path(self, cache_key: str) -> Path:
        return self.cache_dir(cache_key) / "delta_package_full.json"

    def cache_exists(self, cache_key: str) -> bool:
        return (
            self.manifest_path(cache_key).exists()
            and self.package_path(cache_key).exists()
            and self.meta_path(cache_key).exists()
        )

    def resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        store_head = self._candle_store.head_time(series_id)
        if store_head is None:
            raise ServiceError(status_code=404, detail="no_data", code="overlay_replay.no_data")
        requested = int(to_time) if to_time is not None else int(store_head)
        aligned = self._candle_store.floor_time(series_id, at_time=int(requested))
        if aligned is None:
            raise ServiceError(status_code=404, detail="no_data", code="overlay_replay.no_data")
        return int(aligned)

    def ensure_overlay_aligned(self, series_id: str, *, to_time: int) -> None:
        overlay_head = self._overlay_store.head_time(series_id)
        if overlay_head is None or int(overlay_head) < int(to_time):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:overlay",
                code="overlay_replay.ledger_out_of_sync",
            )

    def read_meta(self, cache_key: str) -> OverlayReplayDeltaMetaV1:
        path = self.meta_path(cache_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        return OverlayReplayDeltaMetaV1.model_validate(data)

    def read_full_package(self, cache_key: str) -> OverlayReplayDeltaPackageV1:
        path = self.package_path(cache_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        return OverlayReplayDeltaPackageV1.model_validate(data)

    def read_window(self, *, cache_key: str, target_idx: int) -> OverlayReplayWindowV1:
        if not self.cache_exists(cache_key):
            raise ServiceError(status_code=404, detail="not_found", code="overlay_replay.window.cache_not_found")
        pkg = self.read_full_package(cache_key)
        if not pkg.windows:
            raise ServiceError(status_code=404, detail="not_found", code="overlay_replay.window.not_found")

        idx = int(target_idx)
        if idx < 0 or idx >= int(pkg.delta_meta.total_candles):
            raise ServiceError(
                status_code=422,
                detail="target_idx_out_of_range",
                code="overlay_replay.window.target_idx_out_of_range",
            )

        window_size = int(pkg.delta_meta.window_size)
        window_index = idx // window_size
        if window_index < 0 or window_index >= len(pkg.windows):
            raise ServiceError(
                status_code=422,
                detail="window_index_out_of_range",
                code="overlay_replay.window.window_index_out_of_range",
            )
        return pkg.windows[window_index]
