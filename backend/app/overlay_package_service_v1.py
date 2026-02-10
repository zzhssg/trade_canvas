from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .artifacts import resolve_artifacts_root
from .flags import resolve_env_bool
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


@dataclass
class _Job:
    job_id: str
    cache_key: str
    status: str  # building|done|error
    started_at_ms: int
    finished_at_ms: int | None = None
    error: str | None = None


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
    ) -> None:
        self._candle_store = candle_store
        self._overlay_store = overlay_store
        self._defaults = {
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
        }
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}

    def enabled(self) -> bool:
        return resolve_env_bool("TRADE_CANVAS_ENABLE_REPLAY_PACKAGE", fallback=False)

    def _resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        store_head = self._candle_store.head_time(series_id)
        if store_head is None:
            raise HTTPException(status_code=404, detail="no_data")
        requested = int(to_time) if to_time is not None else int(store_head)
        aligned = self._candle_store.floor_time(series_id, at_time=int(requested))
        if aligned is None:
            raise HTTPException(status_code=404, detail="no_data")
        return int(aligned)

    def _preflight_fail_safe(self, series_id: str, *, to_time: int) -> None:
        """
        Fail-safe alignment guardrail: we must not claim overlay is aligned to to_time
        if overlay store has not been built up to that time.
        """
        overlay_head = self._overlay_store.head_time(series_id)
        if overlay_head is None or int(overlay_head) < int(to_time):
            raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")

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
        return _overlay_pkg_root() / cache_key

    def _manifest_path(self, cache_key: str) -> Path:
        return self._cache_dir(cache_key) / "manifest.json"

    def _meta_path(self, cache_key: str) -> Path:
        return self._cache_dir(cache_key) / "delta_meta.json"

    def _pkg_path(self, cache_key: str) -> Path:
        return self._cache_dir(cache_key) / "delta_package_full.json"

    def cache_exists(self, cache_key: str) -> bool:
        return self._manifest_path(cache_key).exists() and self._pkg_path(cache_key).exists() and self._meta_path(cache_key).exists()

    def read_meta(self, cache_key: str) -> OverlayReplayDeltaMetaV1:
        path = self._meta_path(cache_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        return OverlayReplayDeltaMetaV1.model_validate(data)

    def read_full_package(self, cache_key: str) -> OverlayReplayDeltaPackageV1:
        path = self._pkg_path(cache_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        return OverlayReplayDeltaPackageV1.model_validate(data)

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

        wc = int(window_candles or self._defaults["window_candles"])
        ws = int(window_size or self._defaults["window_size"])
        si = int(snapshot_interval or self._defaults["snapshot_interval"])
        wc = min(2000, max(100, wc))
        ws = min(2000, max(50, ws))
        si = min(200, max(5, si))

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

        wc = int(window_candles or self._defaults["window_candles"])
        ws = int(window_size or self._defaults["window_size"])
        si = int(snapshot_interval or self._defaults["snapshot_interval"])
        wc = min(2000, max(100, wc))
        ws = min(2000, max(50, ws))
        si = min(200, max(5, si))

        cache_key = self._compute_cache_key(series_id, to_time=to_candle_time, window_candles=wc, window_size=ws, snapshot_interval=si)
        job_id = cache_key
        if self.cache_exists(cache_key):
            return ("done", job_id, cache_key)

        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is not None:
                return (existing.status, existing.job_id, existing.cache_key)
            job = _Job(job_id=job_id, cache_key=cache_key, status="building", started_at_ms=int(time.time() * 1000))
            self._jobs[job_id] = job

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

                with self._lock:
                    j = self._jobs.get(job_id)
                    if j is not None:
                        j.status = "done"
                        j.finished_at_ms = int(time.time() * 1000)
            except Exception as e:
                with self._lock:
                    j = self._jobs.get(job_id)
                    if j is not None:
                        j.status = "error"
                        j.error = str(e)
                        j.finished_at_ms = int(time.time() * 1000)

        t = threading.Thread(target=runner, name=f"tc-overlay-replay-{job_id}", daemon=True)
        t.start()
        return ("building", job_id, cache_key)

    def status(self, *, job_id: str, include_delta_package: bool) -> dict[str, Any]:
        job_id = str(job_id)
        with self._lock:
            j = self._jobs.get(job_id)

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
        cache_key = str(job_id)
        if not self.cache_exists(cache_key):
            raise HTTPException(status_code=404, detail="not_found")
        pkg = self.read_full_package(cache_key)
        if not pkg.windows:
            raise HTTPException(status_code=404, detail="not_found")

        idx = int(target_idx)
        if idx < 0 or idx >= int(pkg.delta_meta.total_candles):
            raise HTTPException(status_code=422, detail="target_idx_out_of_range")

        window_size = int(pkg.delta_meta.window_size)
        window_index = idx // window_size
        if window_index < 0 or window_index >= len(pkg.windows):
            raise HTTPException(status_code=422, detail="window_index_out_of_range")
        w = pkg.windows[window_index]
        return w
