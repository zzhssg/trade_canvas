from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from .job_manager import BuildJob


@dataclass(frozen=True)
class WindowParamBounds:
    window_candles_min: int = 100
    window_candles_max: int = 2000
    window_size_min: int = 50
    window_size_max: int = 2000
    snapshot_interval_min: int = 5
    snapshot_interval_max: int = 200


def normalize_window_params(
    *,
    defaults: Mapping[str, int],
    window_candles: int | None,
    window_size: int | None,
    snapshot_interval: int | None,
    bounds: WindowParamBounds,
) -> tuple[int, int, int]:
    wc = int(window_candles or defaults["window_candles"])
    ws = int(window_size or defaults["window_size"])
    si = int(snapshot_interval or defaults["snapshot_interval"])
    wc = min(int(bounds.window_candles_max), max(int(bounds.window_candles_min), wc))
    ws = min(int(bounds.window_size_max), max(int(bounds.window_size_min), ws))
    si = min(int(bounds.snapshot_interval_max), max(int(bounds.snapshot_interval_min), si))
    return wc, ws, si


def normalize_job_identity(job_id: str) -> tuple[str, str]:
    normalized_job_id = str(job_id)
    cache_key = normalized_job_id
    return normalized_job_id, cache_key


def build_status_payload(*, status: str, job_id: str, cache_key: str) -> dict[str, str]:
    return {
        "status": str(status),
        "job_id": str(job_id),
        "cache_key": str(cache_key),
    }


def error_status_payload(
    *,
    job_id: str,
    cache_key: str,
    tracked_job: BuildJob | None,
) -> dict[str, Any]:
    out: dict[str, Any] = build_status_payload(status="error", job_id=job_id, cache_key=cache_key)
    out["error"] = tracked_job.error if tracked_job is not None else "unknown_error"
    return out


def hash_short(payload: str, *, length: int = 24) -> str:
    limit = max(1, int(length))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:limit]
