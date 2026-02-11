from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .dependencies import ReplayPrepareServiceDep, ReplayServiceDep
from .replay_package_protocol_v1 import (
    ReplayBuildRequestV1,
    ReplayBuildResponseV1,
    ReplayCoverageStatusResponseV1,
    ReplayEnsureCoverageRequestV1,
    ReplayEnsureCoverageResponseV1,
    ReplayReadOnlyResponseV1,
    ReplayStatusResponseV1,
    ReplayWindowResponseV1,
)
from .schemas import ReplayPrepareRequestV1, ReplayPrepareResponseV1
from .service_errors import ServiceError, to_http_exception

router = APIRouter()


def _replay_service_or_404(service: ReplayServiceDep) -> ReplayServiceDep:
    if not service.enabled():
        raise HTTPException(status_code=404, detail="not_found")
    return service


@router.post("/api/replay/prepare", response_model=ReplayPrepareResponseV1)
def prepare_replay(
    payload: ReplayPrepareRequestV1,
    replay_prepare_service: ReplayPrepareServiceDep,
) -> ReplayPrepareResponseV1:
    """
    Replay prepare:
    - Ensures factor/overlay ledgers are computed up to aligned time.
    - Returns aligned_time for replay loading.
    """
    try:
        return replay_prepare_service.prepare(payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/replay/read_only", response_model=ReplayReadOnlyResponseV1)
def get_replay_read_only(
    series_id: str = Query(..., min_length=1),
    to_time: int | None = Query(default=None, ge=0),
    window_candles: int | None = Query(default=None, ge=1, le=5000),
    window_size: int | None = Query(default=None, ge=1, le=2000),
    snapshot_interval: int | None = Query(default=None, ge=1, le=200),
    *,
    replay_service: ReplayServiceDep,
) -> ReplayReadOnlyResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        status, job_id, cache_key, coverage, metadata, hint = service.read_only(
            series_id=series_id,
            to_time=to_time,
            window_candles=window_candles,
            window_size=window_size,
            snapshot_interval=snapshot_interval,
        )
        return ReplayReadOnlyResponseV1(
            status=status,
            job_id=job_id,
            cache_key=cache_key,
            coverage=coverage,
            metadata=metadata,
            compute_hint=hint,
        )
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/replay/build", response_model=ReplayBuildResponseV1)
def post_replay_build(
    payload: ReplayBuildRequestV1,
    replay_service: ReplayServiceDep,
) -> ReplayBuildResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        status, job_id, cache_key = service.build(
            series_id=payload.series_id,
            to_time=payload.to_time,
            window_candles=payload.window_candles,
            window_size=payload.window_size,
            snapshot_interval=payload.snapshot_interval,
        )
        return ReplayBuildResponseV1(status=status, job_id=job_id, cache_key=cache_key)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/replay/status", response_model=ReplayStatusResponseV1)
def get_replay_status(
    job_id: str = Query(..., min_length=1),
    include_preload: int = Query(0, ge=0, le=1),
    include_history: int = Query(0, ge=0, le=1),
    *,
    replay_service: ReplayServiceDep,
) -> ReplayStatusResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        payload = service.status(
            job_id=job_id,
            include_preload=bool(include_preload),
            include_history=bool(include_history),
        )
        return ReplayStatusResponseV1.model_validate(payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/replay/window", response_model=ReplayWindowResponseV1)
def get_replay_window(
    job_id: str = Query(..., min_length=1),
    target_idx: int = Query(..., ge=0),
    *,
    replay_service: ReplayServiceDep,
) -> ReplayWindowResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        window = service.window(job_id=job_id, target_idx=int(target_idx))
        head_snapshots, history_deltas = service.window_extras(job_id=job_id, window=window)
        return ReplayWindowResponseV1(
            job_id=str(job_id),
            window=window,
            factor_head_snapshots=head_snapshots,
            history_deltas=history_deltas,
        )
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/replay/ensure_coverage", response_model=ReplayEnsureCoverageResponseV1)
def post_replay_ensure_coverage(
    payload: ReplayEnsureCoverageRequestV1,
    replay_service: ReplayServiceDep,
) -> ReplayEnsureCoverageResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        status, job_id = service.ensure_coverage(
            series_id=payload.series_id,
            target_candles=payload.target_candles,
            to_time=payload.to_time,
        )
        return ReplayEnsureCoverageResponseV1(status=status, job_id=job_id)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


@router.get("/api/replay/coverage_status", response_model=ReplayCoverageStatusResponseV1)
def get_replay_coverage_status(
    job_id: str = Query(..., min_length=1),
    *,
    replay_service: ReplayServiceDep,
) -> ReplayCoverageStatusResponseV1:
    service = _replay_service_or_404(replay_service)
    try:
        payload = service.coverage_status(job_id=job_id)
        if payload.get("status") == "error" and payload.get("error") == "not_found":
            raise HTTPException(status_code=404, detail="not_found")
        return ReplayCoverageStatusResponseV1.model_validate(payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_replay_routes(app: FastAPI) -> None:
    app.include_router(router)
