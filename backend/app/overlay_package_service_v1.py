from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from .artifacts import resolve_artifacts_root
from .build_job_manager import BuildJobManager
from .overlay_package_reader_v1 import OverlayPackageReaderV1
from .overlay_package_builder_v1 import OverlayReplayBuildParamsV1, build_overlay_replay_package_v1, stable_json_dumps
from .overlay_replay_protocol_v1 import (
    OverlayReplayDeltaMetaV1,
    OverlayReplayDeltaPackageV1,
    OverlayReplayWindowV1,
)
from .overlay_store import OverlayStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _overlay_pkg_root() -> Path:
    return resolve_artifacts_root() / "overlay_replay_package_v1"


class OverlayReplayPackageServiceV1:
    """
    Disk-cached overlay replay package builder (v1).

    Key constraints:
    - read-only path must not implicitly compute; cache miss returns build_required
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
        self._candle_store = candle_store
        self._overlay_store = overlay_store
        self._replay_package_enabled = bool(replay_package_enabled)
        self._defaults = {
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
        }
        self._reader = OverlayPackageReaderV1(
            candle_store=self._candle_store,
            overlay_store=self._overlay_store,
            root_dir=_overlay_pkg_root(),
        )
        self._build_jobs = BuildJobManager()

    def enabled(self) -> bool:
        return bool(self._replay_package_enabled)

    def _resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        return self._reader.resolve_to_time(series_id, to_time)

    def _preflight_fail_safe(self, series_id: str, *, to_time: int) -> None:
        self._reader.ensure_overlay_aligned(series_id, to_time=to_time)

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
        h = hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()
        # Keep it short but collision-resistant enough for local artifacts.
        return h[:24]

    def _cache_dir(self, cache_key: str) -> Path:
        return self._reader.cache_dir(cache_key)

    def _manifest_path(self, cache_key: str) -> Path:
        return self._reader.manifest_path(cache_key)

    def _meta_path(self, cache_key: str) -> Path:
        return self._reader.meta_path(cache_key)

    def _pkg_path(self, cache_key: str) -> Path:
        return self._reader.package_path(cache_key)

    def cache_exists(self, cache_key: str) -> bool:
        return self._reader.cache_exists(cache_key)

    def read_meta(self, cache_key: str) -> OverlayReplayDeltaMetaV1:
        return self._reader.read_meta(cache_key)

    def read_full_package(self, cache_key: str) -> OverlayReplayDeltaPackageV1:
        return self._reader.read_full_package(cache_key)

    def _normalize_window_params(
        self,
        *,
        window_candles: int | None,
        window_size: int | None,
        snapshot_interval: int | None,
    ) -> tuple[int, int, int]:
        wc = int(window_candles or self._defaults["window_candles"])
        ws = int(window_size or self._defaults["window_size"])
        si = int(snapshot_interval or self._defaults["snapshot_interval"])
        wc = min(2000, max(100, wc))
        ws = min(2000, max(50, ws))
        si = min(200, max(5, si))
        return (wc, ws, si)

    def read_only(
        self,
        *,
        series_id: str,
        to_time: int | None,
        window_candles: int | None = None,
        window_size: int | None = None,
        snapshot_interval: int | None = None,
    ) -> tuple[str, str, str, OverlayReplayDeltaMetaV1 | None, str | None]:
        """
        Returns: (status, job_id, cache_key, delta_meta, compute_hint)

        status:
          - done
          - build_required
        """
        to_candle_time = self._resolve_to_time(series_id, to_time)
        self._preflight_fail_safe(series_id, to_time=to_candle_time)

        wc, ws, si = self._normalize_window_params(
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )

        cache_key = self._compute_cache_key(series_id, to_time=to_candle_time, window_candles=wc, window_size=ws, snapshot_interval=si)
        job_id = cache_key
        if self.cache_exists(cache_key):
            return ("done", job_id, cache_key, self.read_meta(cache_key), None)
        hint = "build_required: overlay replay package is not cached; click Build to generate it"
        return ("build_required", job_id, cache_key, None, hint)

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
        to_candle_time = self._resolve_to_time(series_id, to_time)
        self._preflight_fail_safe(series_id, to_time=to_candle_time)

        wc, ws, si = self._normalize_window_params(
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )

        cache_key = self._compute_cache_key(series_id, to_time=to_candle_time, window_candles=wc, window_size=ws, snapshot_interval=si)
        job_id = cache_key
        if self.cache_exists(cache_key):
            return ("done", job_id, cache_key)

        existing, created = self._build_jobs.ensure(job_id=job_id, cache_key=cache_key)
        if not created:
            return (existing.status, existing.job_id, existing.cache_key)

        def runner() -> None:
            try:
                pkg_root = self._cache_dir(cache_key)
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
                self._manifest_path(cache_key).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
                self._meta_path(cache_key).write_text(
                    json.dumps(pkg.delta_meta.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                self._pkg_path(cache_key).write_text(
                    json.dumps(pkg.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

                self._build_jobs.mark_done(job_id=job_id)
            except Exception as e:
                self._build_jobs.mark_error(job_id=job_id, error=str(e))

        t = threading.Thread(target=runner, name=f"tc-overlay-replay-{job_id}", daemon=True)
        t.start()
        return ("building", job_id, cache_key)

    def status(self, *, job_id: str, include_delta_package: bool) -> dict[str, Any]:
        job_id = str(job_id)
        j = self._build_jobs.get(job_id)
        cache_key = job_id
        if j is None:
            # Process may have restarted; if cache exists treat as done, else build_required.
            if self.cache_exists(cache_key):
                meta = self.read_meta(cache_key)
                out: dict[str, Any] = {
                    "status": "done",
                    "job_id": job_id,
                    "cache_key": cache_key,
                    "delta_meta": meta.model_dump(mode="json"),
                }
                if include_delta_package:
                    pkg = self.read_full_package(cache_key)
                    out["kline"] = [b.model_dump(mode="json") for w in pkg.windows for b in (w.kline or [])]
                    out["preload_window"] = pkg.windows[0].model_dump(mode="json") if pkg.windows else None
                return out
            return {"status": "build_required", "job_id": job_id, "cache_key": cache_key}

        if j.status == "done":
            meta = self.read_meta(cache_key) if self.cache_exists(cache_key) else None
            out2: dict[str, Any] = {
                "status": "done",
                "job_id": job_id,
                "cache_key": cache_key,
                "delta_meta": meta.model_dump(mode="json") if meta else None,
            }
            if include_delta_package and self.cache_exists(cache_key):
                pkg = self.read_full_package(cache_key)
                out2["kline"] = [b.model_dump(mode="json") for w in pkg.windows for b in (w.kline or [])]
                out2["preload_window"] = pkg.windows[0].model_dump(mode="json") if pkg.windows else None
            return out2

        if j.status == "error":
            return {"status": "error", "job_id": job_id, "cache_key": cache_key, "error": j.error or "unknown_error"}

        # building
        return {"status": "building", "job_id": job_id, "cache_key": cache_key}

    def window(self, *, job_id: str, target_idx: int) -> OverlayReplayWindowV1:
        return self._reader.read_window(cache_key=str(job_id), target_idx=int(target_idx))
