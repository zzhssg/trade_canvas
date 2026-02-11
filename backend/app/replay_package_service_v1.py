from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import resolve_artifacts_root
from .build_job_manager import BuildJobManager
from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .history_bootstrapper import backfill_tail_from_freqtrade
from .market_backfill import backfill_from_ccxt_range
from .replay_package_builder_v1 import ReplayBuildParamsV1, build_replay_package_v1, stable_json_dumps
from .replay_package_reader_v1 import ReplayPackageReaderV1
from .replay_package_protocol_v1 import (
    ReplayCoverageV1,
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayPackageMetadataV1,
    ReplayWindowV1,
)
from .overlay_store import OverlayStore
from .pipelines import IngestPipeline
from .service_errors import ServiceError
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _replay_pkg_root() -> Path:
    return resolve_artifacts_root() / "replay_package_v1"


@dataclass
class _CoverageJob:
    job_id: str
    status: str  # building|done|error
    required_candles: int
    candles_ready: int
    head_time: int | None = None
    started_at_ms: int = 0
    finished_at_ms: int | None = None
    error: str | None = None


class ReplayPackageServiceV1:
    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        overlay_store: OverlayStore,
        factor_slices_service: FactorSlicesService,
        window_candles: int = 2000,
        window_size: int = 500,
        snapshot_interval: int = 25,
        ingest_pipeline: IngestPipeline | None = None,
        replay_enabled: bool = False,
        coverage_enabled: bool = False,
        ccxt_backfill_enabled: bool = False,
        market_history_source: str = "",
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._overlay_store = overlay_store
        self._factor_slices_service = factor_slices_service
        self._ingest_pipeline = ingest_pipeline
        self._replay_enabled = bool(replay_enabled)
        self._coverage_enabled = bool(coverage_enabled)
        self._ccxt_backfill_enabled = bool(ccxt_backfill_enabled)
        self._market_history_source = str(market_history_source).strip().lower()
        self._defaults = {
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
        }
        self._reader = ReplayPackageReaderV1(candle_store=self._candle_store, root_dir=_replay_pkg_root())
        self._build_jobs = BuildJobManager()
        self._coverage_lock = threading.Lock()
        self._coverage_jobs: dict[str, _CoverageJob] = {}

    def enabled(self) -> bool:
        return bool(self._replay_enabled)

    def coverage_enabled(self) -> bool:
        return bool(self._coverage_enabled)

    def _cache_dir(self, cache_key: str) -> Path:
        return self._reader.cache_dir(cache_key)

    def _db_path(self, cache_key: str) -> Path:
        return self._reader.db_path(cache_key)

    def cache_exists(self, cache_key: str) -> bool:
        return self._reader.cache_exists(cache_key)

    def _resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        return self._reader.resolve_to_time(series_id, to_time)

    def _coverage(
        self,
        *,
        series_id: str,
        to_time: int,
        target_candles: int,
    ) -> ReplayCoverageV1:
        return self._reader.coverage(series_id=series_id, to_time=to_time, target_candles=target_candles)

    def _compute_cache_key(
        self,
        *,
        series_id: str,
        to_time: int,
        window_candles: int,
        window_size: int,
        snapshot_interval: int,
    ) -> str:
        payload = {
            "schema": "replay_package_v1",
            "series_id": series_id,
            "to_candle_time": int(to_time),
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
            "candle_store_head_time": int(self._candle_store.head_time(series_id) or 0),
            "factor_store_last_event_id": int(self._factor_store.last_event_id(series_id)),
            "overlay_store_last_version_id": int(self._overlay_store.last_version_id(series_id)),
        }
        h = stable_json_dumps(payload)
        return _hash_short(h)

    def _read_meta(self, cache_key: str) -> ReplayPackageMetadataV1:
        return self._reader.read_meta(cache_key)

    def _read_history_events(self, cache_key: str) -> list[ReplayHistoryEventV1]:
        return self._reader.read_history_events(cache_key)

    def _read_window(self, cache_key: str, *, target_idx: int) -> ReplayWindowV1:
        return self._reader.read_window(cache_key, target_idx=target_idx)

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
        wc = min(5000, max(100, wc))
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
    ) -> tuple[str, str, str, ReplayCoverageV1, ReplayPackageMetadataV1 | None, str | None]:
        to_candle_time = self._resolve_to_time(series_id, to_time)
        wc, ws, si = self._normalize_window_params(
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )

        coverage = self._coverage(series_id=series_id, to_time=to_candle_time, target_candles=wc)
        if coverage.candles_ready < wc:
            cache_key = self._compute_cache_key(
                series_id=series_id,
                to_time=to_candle_time,
                window_candles=wc,
                window_size=ws,
                snapshot_interval=si,
            )
            return ("coverage_missing", cache_key, cache_key, coverage, None, "coverage_missing: not enough closed candles")

        factor_head = self._factor_store.head_time(series_id)
        overlay_head = self._overlay_store.head_time(series_id)
        if factor_head is None or overlay_head is None or int(factor_head) < int(to_candle_time) or int(overlay_head) < int(to_candle_time):
            cache_key = self._compute_cache_key(
                series_id=series_id,
                to_time=to_candle_time,
                window_candles=wc,
                window_size=ws,
                snapshot_interval=si,
            )
            return ("out_of_sync", cache_key, cache_key, coverage, None, "out_of_sync: ledger not ready")

        cache_key = self._compute_cache_key(
            series_id=series_id,
            to_time=to_candle_time,
            window_candles=wc,
            window_size=ws,
            snapshot_interval=si,
        )
        job_id = cache_key
        if self.cache_exists(cache_key):
            return ("done", job_id, cache_key, coverage, self._read_meta(cache_key), None)
        return ("build_required", job_id, cache_key, coverage, None, "build_required: replay package not cached")

    def build(
        self,
        *,
        series_id: str,
        to_time: int | None,
        window_candles: int | None = None,
        window_size: int | None = None,
        snapshot_interval: int | None = None,
    ) -> tuple[str, str, str]:
        to_candle_time = self._resolve_to_time(series_id, to_time)
        wc, ws, si = self._normalize_window_params(
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )

        cache_key = self._compute_cache_key(
            series_id=series_id,
            to_time=to_candle_time,
            window_candles=wc,
            window_size=ws,
            snapshot_interval=si,
        )
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
                db_path = self._db_path(cache_key)
                if db_path.exists():
                    db_path.unlink()

                build_replay_package_v1(
                    db_path=db_path,
                    cache_key=cache_key,
                    candle_store=self._candle_store,
                    factor_store=self._factor_store,
                    overlay_store=self._overlay_store,
                    factor_slices_service=self._factor_slices_service,
                    params=ReplayBuildParamsV1(
                        series_id=series_id,
                        to_candle_time=int(to_candle_time),
                        window_candles=int(wc),
                        window_size=int(ws),
                        snapshot_interval=int(si),
                        preload_offset=0,
                    ),
                )
                self._build_jobs.mark_done(job_id=job_id)
            except Exception as e:
                self._build_jobs.mark_error(job_id=job_id, error=str(e))

        t = threading.Thread(target=runner, name=f"tc-replay-package-{job_id}", daemon=True)
        t.start()
        return ("building", job_id, cache_key)

    def status(self, *, job_id: str, include_preload: bool, include_history: bool) -> dict[str, Any]:
        job_id = str(job_id)
        j = self._build_jobs.get(job_id)
        cache_key = job_id
        if j is None:
            if self.cache_exists(cache_key):
                meta = self._read_meta(cache_key)
                out: dict[str, Any] = {
                    "status": "done",
                    "job_id": job_id,
                    "cache_key": cache_key,
                    "metadata": meta.model_dump(mode="json"),
                }
                if include_preload:
                    preload = self._read_preload_window(cache_key, meta)
                    out["preload_window"] = preload.model_dump(mode="json") if preload else None
                if include_history:
                    out["history_events"] = [e.model_dump(mode="json") for e in self._read_history_events(cache_key)]
                return out
            return {"status": "build_required", "job_id": job_id, "cache_key": cache_key}

        if j.status == "done":
            done_meta: ReplayPackageMetadataV1 | None = self._read_meta(cache_key) if self.cache_exists(cache_key) else None
            out2: dict[str, Any] = {
                "status": "done",
                "job_id": job_id,
                "cache_key": cache_key,
                "metadata": done_meta.model_dump(mode="json") if done_meta else None,
            }
            if include_preload and done_meta is not None:
                preload = self._read_preload_window(cache_key, done_meta)
                out2["preload_window"] = preload.model_dump(mode="json") if preload else None
            if include_history:
                out2["history_events"] = [e.model_dump(mode="json") for e in self._read_history_events(cache_key)]
            return out2

        if j.status == "error":
            return {"status": "error", "job_id": job_id, "cache_key": cache_key, "error": j.error or "unknown_error"}

        return {"status": "building", "job_id": job_id, "cache_key": cache_key}

    def window(self, *, job_id: str, target_idx: int) -> ReplayWindowV1:
        cache_key = str(job_id)
        if not self.cache_exists(cache_key):
            raise ServiceError(status_code=404, detail="not_found", code="replay.window.cache_not_found")
        return self._read_window(cache_key, target_idx=int(target_idx))

    def window_extras(
        self,
        *,
        job_id: str,
        window: ReplayWindowV1,
    ) -> tuple[list[ReplayFactorHeadSnapshotV1], list[ReplayHistoryDeltaV1]]:
        return self._reader.read_window_extras(cache_key=str(job_id), window=window)

    def ensure_coverage(
        self,
        *,
        series_id: str,
        target_candles: int,
        to_time: int | None,
    ) -> tuple[str, str]:
        if not self.coverage_enabled():
            raise ServiceError(status_code=404, detail="not_found", code="replay.coverage.disabled")

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        if to_time is None:
            head = self._candle_store.head_time(series_id)
            if head is not None:
                to_time = int(head)
            else:
                now_s = int(time.time())
                to_time = int(now_s // int(tf_s) * int(tf_s))

        job_id = f"coverage_{series_id}:{int(to_time)}:{int(target_candles)}"
        with self._coverage_lock:
            existing = self._coverage_jobs.get(job_id)
            if existing is not None:
                return (existing.status, existing.job_id)
            job = _CoverageJob(
                job_id=job_id,
                status="building",
                required_candles=int(target_candles),
                candles_ready=0,
                head_time=None,
                started_at_ms=int(time.time() * 1000),
            )
            self._coverage_jobs[job_id] = job

        def runner() -> None:
            try:
                backfill_tail_from_freqtrade(
                    self._candle_store,
                    series_id=series_id,
                    limit=int(target_candles),
                    market_history_source=self._market_history_source,
                )
                if bool(self._ccxt_backfill_enabled):
                    backfill_from_ccxt_range(
                        candle_store=self._candle_store,
                        series_id=series_id,
                        start_time=int(int(to_time or 0) - int(target_candles) * int(tf_s) - int(tf_s)),
                        end_time=int(to_time or 0),
                    )

                if self._ingest_pipeline is None:
                    raise RuntimeError("ingest_pipeline_not_configured")
                self._ingest_pipeline.refresh_series_sync(
                    up_to_times={series_id: int(to_time or 0)},
                )

                cov = self._coverage(series_id=series_id, to_time=int(to_time or 0), target_candles=int(target_candles))
                with self._coverage_lock:
                    j = self._coverage_jobs.get(job_id)
                    if j is not None:
                        j.candles_ready = int(cov.candles_ready)
                        j.head_time = int(self._candle_store.head_time(series_id) or 0)
                        j.status = "done" if cov.candles_ready >= int(target_candles) else "error"
                        j.error = None if j.status == "done" else "coverage_missing"
                        j.finished_at_ms = int(time.time() * 1000)
            except Exception as e:
                with self._coverage_lock:
                    j = self._coverage_jobs.get(job_id)
                    if j is not None:
                        j.status = "error"
                        j.error = str(e)
                        j.finished_at_ms = int(time.time() * 1000)

        t = threading.Thread(target=runner, name=f"tc-replay-coverage-{job_id}", daemon=True)
        t.start()
        return ("building", job_id)

    def coverage_status(self, *, job_id: str) -> dict[str, Any]:
        with self._coverage_lock:
            j = self._coverage_jobs.get(job_id)
        if j is None:
            return {"status": "error", "job_id": job_id, "error": "not_found", "candles_ready": 0, "required_candles": 0}
        return {
            "status": j.status,
            "job_id": j.job_id,
            "candles_ready": int(j.candles_ready),
            "required_candles": int(j.required_candles),
            "head_time": j.head_time,
            "error": j.error,
        }

    def _read_preload_window(self, cache_key: str, meta: ReplayPackageMetadataV1) -> ReplayWindowV1 | None:
        return self._reader.read_preload_window(cache_key, meta)


def _hash_short(payload: str) -> str:
    import hashlib

    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return h[:24]
