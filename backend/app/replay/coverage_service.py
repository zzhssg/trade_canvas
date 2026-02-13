from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..market.history_bootstrapper import backfill_tail_from_freqtrade
from ..market.backfill import backfill_from_ccxt_range
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass
class CoverageJob:
    job_id: str
    status: str
    required_candles: int
    candles_ready: int
    head_time: int | None = None
    started_at_ms: int = 0
    finished_at_ms: int | None = None
    error: str | None = None


class ReplayCoverageCoordinator:
    def __init__(
        self,
        *,
        candle_store: Any,
        ingest_pipeline: Any,
        coverage_fn: Callable[..., Any],
        ccxt_backfill_enabled: bool,
        market_history_source: str,
    ) -> None:
        self._candle_store = candle_store
        self._ingest_pipeline = ingest_pipeline
        self._coverage_fn = coverage_fn
        self._ccxt_backfill_enabled = bool(ccxt_backfill_enabled)
        self._market_history_source = str(market_history_source).strip().lower()
        self._lock = threading.Lock()
        self._jobs: dict[str, CoverageJob] = {}

    def ensure_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> tuple[str, str]:
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
            existing = self._jobs.get(job_id)
            if existing is not None:
                return (existing.status, existing.job_id)
            job = CoverageJob(
                job_id=job_id,
                status="building",
                required_candles=int(target_candles),
                candles_ready=0,
                head_time=None,
                started_at_ms=int(time.time() * 1000),
            )
            self._jobs[job_id] = job
        self._spawn_runner(
            series_id=series_id,
            to_time=int(to_time),
            target_candles=int(target_candles),
            tf_s=int(tf_s),
            job_id=job_id,
        )
        return ("building", job_id)

    def coverage_status(self, *, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return {"status": "error", "job_id": job_id, "error": "not_found", "candles_ready": 0, "required_candles": 0}
        return {
            "status": job.status,
            "job_id": job.job_id,
            "candles_ready": int(job.candles_ready),
            "required_candles": int(job.required_candles),
            "head_time": job.head_time,
            "error": job.error,
        }

    def _spawn_runner(
        self,
        *,
        series_id: str,
        to_time: int,
        target_candles: int,
        tf_s: int,
        job_id: str,
    ) -> None:
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
                        start_time=int(int(to_time) - int(target_candles) * int(tf_s) - int(tf_s)),
                        end_time=int(to_time),
                    )
                if self._ingest_pipeline is None:
                    raise RuntimeError("ingest_pipeline_not_configured")
                self._ingest_pipeline.refresh_series_sync(up_to_times={series_id: int(to_time)})
                cov = self._coverage_fn(series_id=series_id, to_time=int(to_time), target_candles=int(target_candles))
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.candles_ready = int(cov.candles_ready)
                        job.head_time = int(self._candle_store.head_time(series_id) or 0)
                        job.status = "done" if cov.candles_ready >= int(target_candles) else "error"
                        job.error = None if job.status == "done" else "coverage_missing"
                        job.finished_at_ms = int(time.time() * 1000)
            except Exception as exc:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.status = "error"
                        job.error = str(exc)
                        job.finished_at_ms = int(time.time() * 1000)

        thread = threading.Thread(target=runner, name=f"tc-replay-coverage-{job_id}", daemon=True)
        thread.start()
