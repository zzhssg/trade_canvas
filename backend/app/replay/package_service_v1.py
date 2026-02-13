from __future__ import annotations

from pathlib import Path
from typing import Any

from ..build.artifacts import resolve_artifacts_root
from ..factor.slices_service import FactorSlicesService
from ..factor.store import FactorStore
from ..overlay.store import OverlayStore
from ..build.service_base import PackageBuildServiceBase
from ..pipelines import IngestPipeline
from ..core.service_errors import ServiceError
from ..storage.candle_store import CandleStore
from .coverage_service import ReplayCoverageCoordinator
from .package_builder_v1 import ReplayBuildParamsV1, build_replay_package_v1, stable_json_dumps
from .package_protocol_v1 import (
    ReplayCoverageV1,
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayPackageMetadataV1,
    ReplayWindowV1,
)
from .package_reader_v1 import ReplayPackageReaderV1


def _replay_pkg_root() -> Path:
    return resolve_artifacts_root() / "replay_package_v1"


class ReplayPackageServiceV1(PackageBuildServiceBase):
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
        super().__init__()
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
        self._coverage_coordinator = ReplayCoverageCoordinator(
            candle_store=self._candle_store,
            ingest_pipeline=self._ingest_pipeline,
            coverage_fn=lambda *, series_id, to_time, target_candles: self._reader.coverage(
                series_id=series_id,
                to_time=to_time,
                target_candles=target_candles,
            ),
            ccxt_backfill_enabled=bool(self._ccxt_backfill_enabled),
            market_history_source=str(self._market_history_source),
        )

    def enabled(self) -> bool:
        return bool(self._replay_enabled)

    def coverage_enabled(self) -> bool:
        return bool(self._coverage_enabled)

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

    def _preflight_build(
        self,
        *,
        series_id: str,
        to_candle_time: int,
        window_candles: int,
    ) -> ReplayCoverageV1:
        coverage = self._reader.coverage(
            series_id=series_id,
            to_time=to_candle_time,
            target_candles=int(window_candles),
        )
        if coverage.candles_ready < int(window_candles):
            raise ServiceError(
                status_code=409,
                detail="coverage_missing",
                code="replay.build.coverage_missing",
            )

        factor_head = self._factor_store.head_time(series_id)
        overlay_head = self._overlay_store.head_time(series_id)
        if (
            factor_head is None
            or overlay_head is None
            or int(factor_head) < int(to_candle_time)
            or int(overlay_head) < int(to_candle_time)
        ):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:replay",
                code="replay.build.ledger_out_of_sync",
            )
        return coverage

    def build(
        self,
        *,
        series_id: str,
        to_time: int | None,
        window_candles: int | None = None,
        window_size: int | None = None,
        snapshot_interval: int | None = None,
    ) -> tuple[str, str, str]:
        to_candle_time = self._reader.resolve_to_time(series_id, to_time)
        wc, ws, si = self._normalize_window_params(
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )
        self._preflight_build(
            series_id=series_id,
            to_candle_time=to_candle_time,
            window_candles=wc,
        )

        cache_key = self._compute_cache_key(
            series_id=series_id,
            to_time=to_candle_time,
            window_candles=wc,
            window_size=ws,
            snapshot_interval=si,
        )
        reservation = self._reserve_build_job(cache_key=cache_key, cache_exists=self._reader.cache_exists)
        if not reservation.created:
            return (reservation.status, reservation.job_id, reservation.cache_key)

        def _build_package() -> None:
            pkg_root = self._reader.cache_dir(cache_key)
            pkg_root.mkdir(parents=True, exist_ok=True)
            package_path = self._reader.package_path(cache_key)
            if package_path.exists():
                package_path.unlink()

            build_replay_package_v1(
                package_path=package_path,
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

        self._start_tracked_build(
            job_id=reservation.job_id,
            thread_name=f"tc-replay-package-{reservation.job_id}",
            build_fn=_build_package,
        )
        return ("building", reservation.job_id, reservation.cache_key)

    def status(self, *, job_id: str, include_preload: bool, include_history: bool) -> dict[str, Any]:
        normalized_job_id = str(job_id)
        cache_key = normalized_job_id
        status, tracked_job = self._resolve_build_status(
            job_id=normalized_job_id,
            cache_exists=self._reader.cache_exists,
        )
        if status == "build_required":
            raise ServiceError(status_code=404, detail="not_found", code="replay.status.not_found")
        if status == "done":
            done_meta: ReplayPackageMetadataV1 | None = (
                self._reader.read_meta(cache_key) if self._reader.cache_exists(cache_key) else None
            )
            out: dict[str, Any] = {
                "status": "done",
                "job_id": normalized_job_id,
                "cache_key": cache_key,
                "metadata": done_meta.model_dump(mode="json") if done_meta else None,
            }
            if include_preload and done_meta is not None:
                preload = self._read_preload_window(cache_key, done_meta)
                out["preload_window"] = preload.model_dump(mode="json") if preload else None
            if include_history:
                out["history_events"] = [e.model_dump(mode="json") for e in self._reader.read_history_events(cache_key)]
            return out
        if status == "error":
            err = tracked_job.error if tracked_job is not None else None
            return {
                "status": "error",
                "job_id": normalized_job_id,
                "cache_key": cache_key,
                "error": err or "unknown_error",
            }
        return {"status": "building", "job_id": normalized_job_id, "cache_key": cache_key}

    def window(self, *, job_id: str, target_idx: int) -> ReplayWindowV1:
        cache_key = str(job_id)
        if not self._reader.cache_exists(cache_key):
            raise ServiceError(status_code=404, detail="not_found", code="replay.window.cache_not_found")
        return self._reader.read_window(cache_key, target_idx=int(target_idx))

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
        return self._coverage_coordinator.ensure_coverage(
            series_id=series_id,
            target_candles=target_candles,
            to_time=to_time,
        )

    def coverage_status(self, *, job_id: str) -> dict[str, Any]:
        return self._coverage_coordinator.coverage_status(job_id=job_id)

    def _read_preload_window(self, cache_key: str, meta: ReplayPackageMetadataV1) -> ReplayWindowV1 | None:
        return self._reader.read_preload_window(cache_key, meta)


def _hash_short(payload: str) -> str:
    import hashlib

    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return h[:24]
