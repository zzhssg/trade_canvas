from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

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

router = APIRouter()


def _replay_service_or_404(request: Request):
    service = request.app.state.replay_service
    if not service.enabled():
        raise HTTPException(status_code=404, detail="not_found")
    return service


@router.post("/api/replay/prepare", response_model=ReplayPrepareResponseV1)
def prepare_replay(request: Request, payload: ReplayPrepareRequestV1) -> ReplayPrepareResponseV1:
    """
    Replay prepare:
    - Ensures factor/overlay ledgers are computed up to aligned time.
    - Returns aligned_time for replay loading.
    """
    store = request.app.state.store
    series_id = payload.series_id
    store_head = store.head_time(series_id)
    if store_head is None:
        raise HTTPException(status_code=404, detail="no_data")
    requested_time = int(payload.to_time) if payload.to_time is not None else int(store_head)
    aligned = store.floor_time(series_id, at_time=int(requested_time))
    if aligned is None:
        raise HTTPException(status_code=404, detail="no_data")

    window_candles = int(payload.window_candles or 2000)
    window_candles = min(5000, max(100, window_candles))

    runtime = request.app.state.market_runtime
    flags = runtime.flags
    ingest_pipeline = runtime.ingest_pipeline
    computed = False
    factor_head = request.app.state.factor_store.head_time(series_id)
    overlay_head = request.app.state.overlay_store.head_time(series_id)

    if flags.enable_ingest_pipeline_v2 and ingest_pipeline is not None:
        if (
            factor_head is None
            or int(factor_head) < int(aligned)
            or overlay_head is None
            or int(overlay_head) < int(aligned)
        ):
            pipeline_result = ingest_pipeline.refresh_series_sync(
                up_to_times={series_id: int(aligned)}
            )
            computed = bool(pipeline_result.steps)
        factor_head = request.app.state.factor_store.head_time(series_id)
        overlay_head = request.app.state.overlay_store.head_time(series_id)
    else:
        factor_rebuilt = False
        if factor_head is None or int(factor_head) < int(aligned):
            factor_result = request.app.state.factor_orchestrator.ingest_closed(
                series_id=series_id,
                up_to_candle_time=int(aligned),
            )
            factor_rebuilt = bool(getattr(factor_result, "rebuilt", False))
            factor_head = request.app.state.factor_store.head_time(series_id)
            computed = True

        if factor_rebuilt:
            request.app.state.overlay_orchestrator.reset_series(series_id=series_id)
            overlay_head = None

        if overlay_head is None or int(overlay_head) < int(aligned):
            request.app.state.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(aligned))
            overlay_head = request.app.state.overlay_store.head_time(series_id)
            computed = True

    if factor_head is None or int(factor_head) < int(aligned):
        raise HTTPException(status_code=409, detail="ledger_out_of_sync:factor")
    if overlay_head is None or int(overlay_head) < int(aligned):
        raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")

    if flags.enable_debug_api:
        request.app.state.debug_hub.emit(
            pipe="read",
            event="read.http.replay_prepare",
            series_id=series_id,
            message="prepare replay",
            data={
                "requested_time": int(requested_time),
                "aligned_time": int(aligned),
                "window_candles": int(window_candles),
                "factor_head_time": int(factor_head),
                "overlay_head_time": int(overlay_head),
                "computed": bool(computed),
            },
        )

    return ReplayPrepareResponseV1(
        ok=True,
        series_id=series_id,
        requested_time=int(requested_time),
        aligned_time=int(aligned),
        window_candles=int(window_candles),
        factor_head_time=int(factor_head) if factor_head is not None else None,
        overlay_head_time=int(overlay_head) if overlay_head is not None else None,
        computed=bool(computed),
    )


@router.get("/api/replay/read_only", response_model=ReplayReadOnlyResponseV1)
def get_replay_read_only(
    request: Request,
    series_id: str = Query(..., min_length=1),
    to_time: int | None = Query(default=None, ge=0),
    window_candles: int | None = Query(default=None, ge=1, le=5000),
    window_size: int | None = Query(default=None, ge=1, le=2000),
    snapshot_interval: int | None = Query(default=None, ge=1, le=200),
) -> ReplayReadOnlyResponseV1:
    service = _replay_service_or_404(request)
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


@router.post("/api/replay/build", response_model=ReplayBuildResponseV1)
def post_replay_build(request: Request, payload: ReplayBuildRequestV1) -> ReplayBuildResponseV1:
    service = _replay_service_or_404(request)
    status, job_id, cache_key = service.build(
        series_id=payload.series_id,
        to_time=payload.to_time,
        window_candles=payload.window_candles,
        window_size=payload.window_size,
        snapshot_interval=payload.snapshot_interval,
    )
    return ReplayBuildResponseV1(status=status, job_id=job_id, cache_key=cache_key)


@router.get("/api/replay/status", response_model=ReplayStatusResponseV1)
def get_replay_status(
    request: Request,
    job_id: str = Query(..., min_length=1),
    include_preload: int = Query(0, ge=0, le=1),
    include_history: int = Query(0, ge=0, le=1),
) -> ReplayStatusResponseV1:
    service = _replay_service_or_404(request)
    payload = service.status(
        job_id=job_id,
        include_preload=bool(include_preload),
        include_history=bool(include_history),
    )
    return ReplayStatusResponseV1.model_validate(payload)


@router.get("/api/replay/window", response_model=ReplayWindowResponseV1)
def get_replay_window(
    request: Request,
    job_id: str = Query(..., min_length=1),
    target_idx: int = Query(..., ge=0),
) -> ReplayWindowResponseV1:
    service = _replay_service_or_404(request)
    window = service.window(job_id=job_id, target_idx=int(target_idx))
    head_snapshots, history_deltas = service.window_extras(job_id=job_id, window=window)
    return ReplayWindowResponseV1(
        job_id=str(job_id),
        window=window,
        factor_head_snapshots=head_snapshots,
        history_deltas=history_deltas,
    )


@router.post("/api/replay/ensure_coverage", response_model=ReplayEnsureCoverageResponseV1)
def post_replay_ensure_coverage(request: Request, payload: ReplayEnsureCoverageRequestV1) -> ReplayEnsureCoverageResponseV1:
    service = _replay_service_or_404(request)
    status, job_id = service.ensure_coverage(
        series_id=payload.series_id,
        target_candles=payload.target_candles,
        to_time=payload.to_time,
        factor_orchestrator=request.app.state.factor_orchestrator,
        overlay_orchestrator=request.app.state.overlay_orchestrator,
    )
    return ReplayEnsureCoverageResponseV1(status=status, job_id=job_id)


@router.get("/api/replay/coverage_status", response_model=ReplayCoverageStatusResponseV1)
def get_replay_coverage_status(request: Request, job_id: str = Query(..., min_length=1)) -> ReplayCoverageStatusResponseV1:
    service = _replay_service_or_404(request)
    payload = service.coverage_status(job_id=job_id)
    if payload.get("status") == "error" and payload.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="not_found")
    return ReplayCoverageStatusResponseV1.model_validate(payload)


def register_replay_routes(app: FastAPI) -> None:
    app.include_router(router)
