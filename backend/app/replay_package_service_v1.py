from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .history_bootstrapper import backfill_tail_from_freqtrade
from .market_backfill import backfill_from_ccxt_range
from .replay_package_builder_v1 import ReplayBuildParamsV1, build_replay_package_v1, stable_json_dumps
from .replay_package_protocol_v1 import (
    ReplayCoverageV1,
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayKlineBarV1,
    ReplayPackageMetadataV1,
    ReplayWindowV1,
)
from .overlay_store import OverlayStore
from .overlay_replay_protocol_v1 import OverlayReplayCheckpointV1, OverlayReplayDiffV1
from .schemas import OverlayInstructionPatchItemV1
from .sqlite_util import connect as sqlite_connect
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _truthy_flag(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _artifacts_root() -> Path:
    raw = (os.environ.get("TRADE_CANVAS_ARTIFACTS_DIR") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (_repo_root() / p).resolve()
        return p
    return (_repo_root() / "backend" / "data" / "artifacts").resolve()


def _replay_pkg_root() -> Path:
    return _artifacts_root() / "replay_package_v1"


@dataclass
class _Job:
    job_id: str
    cache_key: str
    status: str  # building|done|error
    started_at_ms: int
    finished_at_ms: int | None = None
    error: str | None = None


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
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._overlay_store = overlay_store
        self._factor_slices_service = factor_slices_service
        self._defaults = {
            "window_candles": int(window_candles),
            "window_size": int(window_size),
            "snapshot_interval": int(snapshot_interval),
            "preload_offset": 0,
        }
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._coverage_jobs: dict[str, _CoverageJob] = {}

    def enabled(self) -> bool:
        return _truthy_flag(os.environ.get("TRADE_CANVAS_ENABLE_REPLAY_V1"))

    def coverage_enabled(self) -> bool:
        return _truthy_flag(os.environ.get("TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE"))

    def _cache_dir(self, cache_key: str) -> Path:
        return _replay_pkg_root() / cache_key

    def _db_path(self, cache_key: str) -> Path:
        return self._cache_dir(cache_key) / "replay.sqlite"

    def cache_exists(self, cache_key: str) -> bool:
        return self._db_path(cache_key).exists()

    def _resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        store_head = self._candle_store.head_time(series_id)
        if store_head is None and to_time is None:
            raise HTTPException(status_code=404, detail="no_data")
        requested = int(to_time) if to_time is not None else int(store_head or 0)
        aligned = self._candle_store.floor_time(series_id, at_time=int(requested))
        if aligned is None:
            raise HTTPException(status_code=404, detail="no_data")
        return int(aligned)

    def _coverage(
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
        db_path = self._db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT schema_version, series_id, timeframe_s, total_candles, from_candle_time, to_candle_time,
                       window_size, snapshot_interval, preload_offset, idx_to_time
                FROM replay_meta
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("missing replay_meta")
            return ReplayPackageMetadataV1(
                schema_version=int(row["schema_version"]),
                series_id=str(row["series_id"]),
                timeframe_s=int(row["timeframe_s"]),
                total_candles=int(row["total_candles"]),
                from_candle_time=int(row["from_candle_time"]),
                to_candle_time=int(row["to_candle_time"]),
                window_size=int(row["window_size"]),
                snapshot_interval=int(row["snapshot_interval"]),
                preload_offset=int(row["preload_offset"]),
                idx_to_time=str(row["idx_to_time"]),
            )
        finally:
            conn.close()

    def _read_history_events(self, cache_key: str) -> list[ReplayHistoryEventV1]:
        db_path = self._db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT event_id, factor_name, candle_time, kind, event_key, payload_json
                FROM replay_factor_history_events
                ORDER BY event_id ASC
                """
            ).fetchall()
            out: list[ReplayHistoryEventV1] = []
            for r in rows:
                try:
                    payload = json.loads(r["payload_json"])
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                out.append(
                    ReplayHistoryEventV1(
                        event_id=int(r["event_id"]),
                        factor_name=str(r["factor_name"]),
                        candle_time=int(r["candle_time"]),
                        kind=str(r["kind"]),
                        event_key=str(r["event_key"]),
                        payload=payload,
                    )
                )
            return out
        finally:
            conn.close()

    def _read_window(self, cache_key: str, *, target_idx: int) -> ReplayWindowV1:
        db_path = self._db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            meta = conn.execute(
                "SELECT total_candles, window_size FROM replay_meta LIMIT 1"
            ).fetchone()
            if meta is None:
                raise HTTPException(status_code=404, detail="not_found")
            total = int(meta["total_candles"])
            window_size = int(meta["window_size"])
            idx = int(target_idx)
            if idx < 0 or idx >= total:
                raise HTTPException(status_code=422, detail="target_idx_out_of_range")
            window_index = idx // window_size
            w = conn.execute(
                """
                SELECT window_index, start_idx, end_idx
                FROM replay_window_meta
                WHERE window_index = ?
                """,
                (int(window_index),),
            ).fetchone()
            if w is None:
                raise HTTPException(status_code=404, detail="not_found")
            start_idx = int(w["start_idx"])
            end_idx = int(w["end_idx"])

            kline_rows = conn.execute(
                """
                SELECT idx, candle_time, open, high, low, close, volume
                FROM replay_kline_bars
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            kline = [
                ReplayKlineBarV1(
                    time=int(r["candle_time"]),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
                for r in kline_rows
            ]

            catalog_rows = conn.execute(
                """
                SELECT w.scope, v.version_id, v.instruction_id, v.kind, v.visible_time, v.definition_json
                FROM replay_draw_catalog_window w
                JOIN replay_draw_catalog_versions v ON v.version_id = w.version_id
                WHERE w.window_index = ?
                ORDER BY v.version_id ASC
                """,
                (int(window_index),),
            ).fetchall()
            base: list[OverlayInstructionPatchItemV1] = []
            patch: list[OverlayInstructionPatchItemV1] = []
            for r in catalog_rows:
                try:
                    definition = json.loads(r["definition_json"])
                except Exception:
                    definition = {}
                item = OverlayInstructionPatchItemV1(
                    version_id=int(r["version_id"]),
                    instruction_id=str(r["instruction_id"]),
                    kind=str(r["kind"]),
                    visible_time=int(r["visible_time"]),
                    definition=definition if isinstance(definition, dict) else {},
                )
                if str(r["scope"]) == "base":
                    base.append(item)
                else:
                    patch.append(item)

            checkpoint_rows = conn.execute(
                """
                SELECT at_idx, active_ids_json
                FROM replay_draw_active_checkpoints
                WHERE window_index = ?
                ORDER BY at_idx ASC
                """,
                (int(window_index),),
            ).fetchall()
            checkpoints = []
            for r in checkpoint_rows:
                try:
                    active_ids = json.loads(r["active_ids_json"])
                except Exception:
                    active_ids = []
                checkpoints.append(OverlayReplayCheckpointV1(at_idx=int(r["at_idx"]), active_ids=active_ids or []))

            diff_rows = conn.execute(
                """
                SELECT at_idx, add_ids_json, remove_ids_json
                FROM replay_draw_active_diffs
                WHERE window_index = ?
                ORDER BY at_idx ASC
                """,
                (int(window_index),),
            ).fetchall()
            diffs = []
            for r in diff_rows:
                try:
                    add_ids = json.loads(r["add_ids_json"])
                except Exception:
                    add_ids = []
                try:
                    remove_ids = json.loads(r["remove_ids_json"])
                except Exception:
                    remove_ids = []
                diffs.append(
                    OverlayReplayDiffV1(at_idx=int(r["at_idx"]), add_ids=add_ids or [], remove_ids=remove_ids or [])
                )

            return ReplayWindowV1(
                window_index=int(window_index),
                start_idx=int(start_idx),
                end_idx=int(end_idx),
                kline=kline,
                draw_catalog_base=base,
                draw_catalog_patch=patch,
                draw_active_checkpoints=checkpoints,
                draw_active_diffs=diffs,
            )
        finally:
            conn.close()

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
        wc = int(window_candles or self._defaults["window_candles"])
        ws = int(window_size or self._defaults["window_size"])
        si = int(snapshot_interval or self._defaults["snapshot_interval"])
        wc = min(5000, max(100, wc))
        ws = min(2000, max(50, ws))
        si = min(200, max(5, si))

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
        wc = int(window_candles or self._defaults["window_candles"])
        ws = int(window_size or self._defaults["window_size"])
        si = int(snapshot_interval or self._defaults["snapshot_interval"])
        wc = min(5000, max(100, wc))
        ws = min(2000, max(50, ws))
        si = min(200, max(5, si))

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

        t = threading.Thread(target=runner, name=f"tc-replay-package-{job_id}", daemon=True)
        t.start()
        return ("building", job_id, cache_key)

    def status(self, *, job_id: str, include_preload: bool, include_history: bool) -> dict[str, Any]:
        job_id = str(job_id)
        with self._lock:
            j = self._jobs.get(job_id)

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
            meta = self._read_meta(cache_key) if self.cache_exists(cache_key) else None
            out2: dict[str, Any] = {
                "status": "done",
                "job_id": job_id,
                "cache_key": cache_key,
                "metadata": meta.model_dump(mode="json") if meta else None,
            }
            if include_preload and meta is not None:
                preload = self._read_preload_window(cache_key, meta)
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
            raise HTTPException(status_code=404, detail="not_found")
        return self._read_window(cache_key, target_idx=int(target_idx))

    def window_extras(self, *, job_id: str, window: ReplayWindowV1) -> tuple[list[ReplayFactorHeadSnapshotV1], list[ReplayHistoryDeltaV1]]:
        db_path = self._db_path(str(job_id))
        conn = sqlite_connect(db_path)
        try:
            start_idx = int(window.start_idx)
            end_idx = int(window.end_idx)
            rows = conn.execute(
                """
                SELECT candle_time
                FROM replay_kline_bars
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            times = [int(r["candle_time"]) for r in rows]
            head_rows: list[ReplayFactorHeadSnapshotV1] = []
            if times:
                q = """
                SELECT factor_name, candle_time, seq, head_json
                FROM replay_factor_head_snapshots
                WHERE candle_time >= ? AND candle_time <= ?
                ORDER BY candle_time ASC, factor_name ASC, seq ASC
                """
                for r in conn.execute(q, (int(times[0]), int(times[-1]))).fetchall():
                    try:
                        head = json.loads(r["head_json"])
                    except Exception:
                        head = {}
                    head_rows.append(
                        ReplayFactorHeadSnapshotV1(
                            factor_name=str(r["factor_name"]),
                            candle_time=int(r["candle_time"]),
                            seq=int(r["seq"]),
                            head=head if isinstance(head, dict) else {},
                        )
                    )

            delta_rows = conn.execute(
                """
                SELECT idx, from_event_id, to_event_id
                FROM replay_factor_history_deltas
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            deltas = [
                ReplayHistoryDeltaV1(
                    idx=int(r["idx"]),
                    from_event_id=int(r["from_event_id"]),
                    to_event_id=int(r["to_event_id"]),
                )
                for r in delta_rows
            ]
            return (head_rows, deltas)
        finally:
            conn.close()

    def ensure_coverage(
        self,
        *,
        series_id: str,
        target_candles: int,
        to_time: int | None,
        factor_orchestrator,
        overlay_orchestrator,
    ) -> tuple[str, str]:
        if not self.coverage_enabled():
            raise HTTPException(status_code=404, detail="not_found")

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        if to_time is None:
            head = self._candle_store.head_time(series_id)
            if head is not None:
                to_time = int(head)
            else:
                now_s = int(time.time())
                to_time = int(now_s // int(tf_s) * int(tf_s))

        job_id = f"coverage_{series_id}:{int(to_time)}:{int(target_candles)}"
        with self._lock:
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
                backfill_tail_from_freqtrade(self._candle_store, series_id=series_id, limit=int(target_candles))
                if _truthy_flag(os.environ.get("TRADE_CANVAS_ENABLE_CCXT_BACKFILL")):
                    backfill_from_ccxt_range(
                        candle_store=self._candle_store,
                        series_id=series_id,
                        start_time=int(int(to_time or 0) - int(target_candles) * int(tf_s) - int(tf_s)),
                        end_time=int(to_time or 0),
                    )

                factor_rebuilt = False
                if factor_orchestrator is not None:
                    try:
                        factor_result = factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_time or 0))
                        factor_rebuilt = bool(getattr(factor_result, "rebuilt", False))
                    except Exception:
                        pass
                if overlay_orchestrator is not None:
                    try:
                        if factor_rebuilt:
                            overlay_orchestrator.reset_series(series_id=series_id)
                        overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_time or 0))
                    except Exception:
                        pass

                cov = self._coverage(series_id=series_id, to_time=int(to_time or 0), target_candles=int(target_candles))
                with self._lock:
                    j = self._coverage_jobs.get(job_id)
                    if j is not None:
                        j.candles_ready = int(cov.candles_ready)
                        j.head_time = int(self._candle_store.head_time(series_id) or 0)
                        j.status = "done" if cov.candles_ready >= int(target_candles) else "error"
                        j.error = None if j.status == "done" else "coverage_missing"
                        j.finished_at_ms = int(time.time() * 1000)
            except Exception as e:
                with self._lock:
                    j = self._coverage_jobs.get(job_id)
                    if j is not None:
                        j.status = "error"
                        j.error = str(e)
                        j.finished_at_ms = int(time.time() * 1000)

        t = threading.Thread(target=runner, name=f"tc-replay-coverage-{job_id}", daemon=True)
        t.start()
        return ("building", job_id)

    def coverage_status(self, *, job_id: str) -> dict[str, Any]:
        with self._lock:
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
        if meta.total_candles <= 0:
            return None
        target_idx = max(0, int(meta.total_candles) - 1 - int(meta.preload_offset))
        return self._read_window(cache_key, target_idx=int(target_idx))


def _hash_short(payload: str) -> str:
    import hashlib

    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return h[:24]
