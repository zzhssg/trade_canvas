from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query

from .dependencies import OverlayPackageServiceDep
from .overlay_replay_protocol_v1 import (
    ReplayOverlayPackageBuildRequestV1,
    ReplayOverlayPackageBuildResponseV1,
    ReplayOverlayPackageReadOnlyRequestV1,
    ReplayOverlayPackageReadOnlyResponseV1,
    ReplayOverlayPackageStatusResponseV1,
    ReplayOverlayPackageWindowResponseV1,
)

router = APIRouter()


def _overlay_pkg_service_or_404(service: OverlayPackageServiceDep):
    if not service.enabled():
        raise HTTPException(status_code=404, detail="not_found")
    return service


@router.get("/api/replay/overlay_package/read_only", response_model=ReplayOverlayPackageReadOnlyResponseV1)
def replay_overlay_package_read_only(
    req: ReplayOverlayPackageReadOnlyRequestV1 = Depends(),
    *,
    overlay_pkg_service: OverlayPackageServiceDep,
) -> ReplayOverlayPackageReadOnlyResponseV1:
    service = _overlay_pkg_service_or_404(overlay_pkg_service)
    status, job_id, cache_key, meta, hint = service.read_only(
        series_id=req.series_id,
        to_time=req.to_time,
        window_candles=req.window_candles,
        window_size=req.window_size,
        snapshot_interval=req.snapshot_interval,
    )
    return ReplayOverlayPackageReadOnlyResponseV1(
        status=status,
        job_id=job_id,
        cache_key=cache_key,
        delta_meta=meta,
        compute_hint=hint,
    )


@router.post("/api/replay/overlay_package/build", response_model=ReplayOverlayPackageBuildResponseV1)
def replay_overlay_package_build(
    req: ReplayOverlayPackageBuildRequestV1,
    overlay_pkg_service: OverlayPackageServiceDep,
) -> ReplayOverlayPackageBuildResponseV1:
    service = _overlay_pkg_service_or_404(overlay_pkg_service)
    status, job_id, cache_key = service.build(
        series_id=req.series_id,
        to_time=req.to_time,
        window_candles=req.window_candles,
        window_size=req.window_size,
        snapshot_interval=req.snapshot_interval,
    )
    return ReplayOverlayPackageBuildResponseV1(status=status, job_id=job_id, cache_key=cache_key)


@router.get("/api/replay/overlay_package/status", response_model=ReplayOverlayPackageStatusResponseV1)
def replay_overlay_package_status(
    job_id: str = Query(..., min_length=1),
    include_delta_package: int = Query(0, ge=0, le=1),
    *,
    overlay_pkg_service: OverlayPackageServiceDep,
) -> ReplayOverlayPackageStatusResponseV1:
    service = _overlay_pkg_service_or_404(overlay_pkg_service)
    payload = service.status(
        job_id=job_id,
        include_delta_package=bool(int(include_delta_package)),
    )
    return ReplayOverlayPackageStatusResponseV1.model_validate(payload)


@router.get("/api/replay/overlay_package/window", response_model=ReplayOverlayPackageWindowResponseV1)
def replay_overlay_package_window(
    job_id: str = Query(..., min_length=1),
    target_idx: int = Query(..., ge=0),
    *,
    overlay_pkg_service: OverlayPackageServiceDep,
) -> ReplayOverlayPackageWindowResponseV1:
    service = _overlay_pkg_service_or_404(overlay_pkg_service)
    window = service.window(job_id=job_id, target_idx=int(target_idx))
    return ReplayOverlayPackageWindowResponseV1(job_id=str(job_id), window=window)


def register_overlay_package_routes(app: FastAPI) -> None:
    app.include_router(router)
