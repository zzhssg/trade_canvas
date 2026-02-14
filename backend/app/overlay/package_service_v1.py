from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..build.artifacts import resolve_artifacts_root
from ..build.service_base import PackageBuildServiceBase
from ..build.package_service_helpers import (
    WindowParamBounds,
    build_status_payload,
    error_status_payload,
    hash_short,
    normalize_job_identity,
    normalize_window_params,
)
from ..core.service_errors import ServiceError
from ..storage.candle_store import CandleStore
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds
from .package_builder_v1 import OverlayReplayBuildParamsV1, build_overlay_replay_package_v1, stable_json_dumps
from .package_reader_v1 import OverlayPackageReaderV1
from .replay_protocol_v1 import OverlayReplayWindowV1
from .store import OverlayStore


def _overlay_pkg_root() -> Path:
    return resolve_artifacts_root() / "overlay_replay_package_v1"


class OverlayReplayPackageServiceV1(PackageBuildServiceBase):
    """
    Disk-cached overlay replay package builder (v1).

    Key constraints:
    - build is explicit; output is reproducible (stable cache_key)
    - window API serves window slices with catalog_base/patch + checkpoints/diffs
    """

    def __init__(
        self,
        *,
        candle_store: CandleStore,
        overlay_store: OverlayStore,
        window_candles: int = 2000,
        window_size: int = 500,
        snapshot_interval: int = 25,
        replay_package_enabled: bool = False,
    ) -> None:
        super().__init__()
        self._candle_store = candle_store
        self._overlay_store = overlay_store
        self._replay_package_enabled = bool(replay_package_enabled)
        self._defaults = {
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
        }
        self._window_param_bounds = WindowParamBounds(window_candles_max=2000)
        self._reader = OverlayPackageReaderV1(
            candle_store=self._candle_store,
            overlay_store=self._overlay_store,
            root_dir=_overlay_pkg_root(),
        )

    def enabled(self) -> bool:
        return bool(self._replay_package_enabled)

    def _compute_cache_key(self, series_id: str, *, to_time: int, window_candles: int, window_size: int, snapshot_interval: int) -> str:
        overlay_last_version_id = int(self._overlay_store.last_version_id(series_id))
        payload = {
            "schema": "overlay_replay_package_v1",
            "series_id": series_id,
            "to_candle_time": int(to_time),
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
            "overlay_store_last_version_id": int(overlay_last_version_id),
        }
        return hash_short(stable_json_dumps(payload))

    def build(
        self,
        *,
        series_id: str,
        to_time: int | None,
        window_candles: int | None = None,
        window_size: int | None = None,
        snapshot_interval: int | None = None,
    ) -> tuple[str, str, str]:
        """
        Returns: (status, job_id, cache_key)
        status:
          - building
          - done
        """
        to_candle_time = self._reader.resolve_to_time(series_id, to_time)
        self._reader.ensure_overlay_aligned(series_id, to_time=to_candle_time)

        wc, ws, si = normalize_window_params(
            defaults=self._defaults,
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
            bounds=self._window_param_bounds,
        )

        cache_key = self._compute_cache_key(series_id, to_time=to_candle_time, window_candles=wc, window_size=ws, snapshot_interval=si)
        reservation = self._reserve_build_job(cache_key=cache_key, cache_exists=self._reader.cache_exists)
        if not reservation.created:
            return (reservation.status, reservation.job_id, reservation.cache_key)

        def _build_package() -> None:
            pkg_root = self._reader.cache_dir(cache_key)
            pkg_root.mkdir(parents=True, exist_ok=True)

            tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
            manifest = {
                "schema_version": 1,
                "cache_key": cache_key,
                "series_id": series_id,
                "to_candle_time": int(to_candle_time),
                "timeframe_s": int(tf_s),
                "window_candles": int(wc),
                "window_size": int(ws),
                "snapshot_interval": int(si),
                "preload_offset": 0,
                "overlay_store_last_version_id": int(self._overlay_store.last_version_id(series_id)),
                "builder_version": 1,
                "created_at_ms": int(time.time() * 1000),
            }
            self._reader.manifest_path(cache_key).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            pkg = build_overlay_replay_package_v1(
                candle_store=self._candle_store,
                overlay_store=self._overlay_store,
                params=OverlayReplayBuildParamsV1(
                    series_id=series_id,
                    to_candle_time=int(to_candle_time),
                    window_candles=int(wc),
                    window_size=int(ws),
                    snapshot_interval=int(si),
                    preload_offset=0,
                ),
            )
            self._reader.meta_path(cache_key).write_text(
                json.dumps(pkg.delta_meta.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._reader.package_path(cache_key).write_text(
                json.dumps(pkg.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        self._start_tracked_build(
            job_id=reservation.job_id,
            thread_name=f"tc-overlay-replay-{reservation.job_id}",
            build_fn=_build_package,
        )
        return ("building", reservation.job_id, reservation.cache_key)

    def status(self, *, job_id: str, include_delta_package: bool) -> dict[str, Any]:
        normalized_job_id, cache_key = normalize_job_identity(job_id)
        status, tracked_job = self._resolve_build_status(
            job_id=normalized_job_id,
            cache_exists=self._reader.cache_exists,
        )
        if status == "build_required":
            raise ServiceError(status_code=404, detail="not_found", code="overlay_replay.status.not_found")
        if status == "done":
            done_meta = self._reader.read_meta(cache_key) if self._reader.cache_exists(cache_key) else None
            out: dict[str, Any] = build_status_payload(status="done", job_id=normalized_job_id, cache_key=cache_key)
            out["delta_meta"] = done_meta.model_dump(mode="json") if done_meta else None
            if include_delta_package and self._reader.cache_exists(cache_key):
                pkg = self._reader.read_full_package(cache_key)
                out["kline"] = [b.model_dump(mode="json") for w in pkg.windows for b in (w.kline or [])]
                out["preload_window"] = pkg.windows[0].model_dump(mode="json") if pkg.windows else None
            return out
        if status == "error":
            return error_status_payload(job_id=normalized_job_id, cache_key=cache_key, tracked_job=tracked_job)
        return build_status_payload(status="building", job_id=normalized_job_id, cache_key=cache_key)

    def window(self, *, job_id: str, target_idx: int) -> OverlayReplayWindowV1:
        return self._reader.read_window(cache_key=str(job_id), target_idx=int(target_idx))
