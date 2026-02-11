from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from .dependencies import MarketIngestServiceDep, RuntimeFlagsDep, WorktreeManagerDep
from .schemas import (
    DevCreateWorktreeRequest,
    DevCreateWorktreeResponse,
    DevDeleteWorktreeRequest,
    DevDeleteWorktreeResponse,
    DevPortAllocationResponse,
    DevServiceState,
    DevServiceStatus,
    DevStartServicesRequest,
    DevStartServicesResponse,
    DevStopServicesResponse,
    DevUpdateMetadataRequest,
    DevUpdateMetadataResponse,
    DevWorktreeInfo,
    DevWorktreeListResponse,
    DevWorktreeMetadata,
    IngestCandlesClosedBatchRequest,
    IngestCandlesClosedBatchResponse,
)
from .service_errors import ServiceError, to_http_exception


def _require_dev_api_enabled(runtime_flags: RuntimeFlagsDep) -> None:
    if not bool(runtime_flags.enable_dev_api):
        raise HTTPException(status_code=404, detail="not_found")


router = APIRouter(dependencies=[Depends(_require_dev_api_enabled)])
logger = logging.getLogger(__name__)


def _worktree_to_response(wt) -> DevWorktreeInfo:
    metadata = None
    if wt.metadata:
        metadata = DevWorktreeMetadata(
            description=wt.metadata.description,
            plan_path=wt.metadata.plan_path,
            created_at=wt.metadata.created_at,
            owner=wt.metadata.owner,
            ports=wt.metadata.ports,
        )
    services = None
    if wt.services:
        services = DevServiceStatus(
            backend=DevServiceState(
                running=wt.services.backend.running,
                port=wt.services.backend.port,
                pid=wt.services.backend.pid,
                url=wt.services.backend.url,
            ),
            frontend=DevServiceState(
                running=wt.services.frontend.running,
                port=wt.services.frontend.port,
                pid=wt.services.frontend.pid,
                url=wt.services.frontend.url,
            ),
        )
    return DevWorktreeInfo(
        id=wt.id,
        path=wt.path,
        branch=wt.branch,
        commit=wt.commit,
        is_detached=wt.is_detached,
        is_main=wt.is_main,
        metadata=metadata,
        services=services,
    )


@router.get("/api/dev/worktrees", response_model=DevWorktreeListResponse)
def list_worktrees(worktree_manager: WorktreeManagerDep) -> DevWorktreeListResponse:
    worktrees = worktree_manager.list_worktrees()
    return DevWorktreeListResponse(worktrees=[_worktree_to_response(wt) for wt in worktrees])


@router.get("/api/dev/worktrees/{worktree_id}", response_model=DevWorktreeInfo)
def get_worktree(worktree_id: str, worktree_manager: WorktreeManagerDep) -> DevWorktreeInfo:
    wt = worktree_manager.get_worktree(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree_not_found")
    return _worktree_to_response(wt)


@router.post("/api/dev/worktrees", response_model=DevCreateWorktreeResponse)
def create_worktree(req: DevCreateWorktreeRequest, worktree_manager: WorktreeManagerDep) -> DevCreateWorktreeResponse:
    try:
        wt = worktree_manager.create_worktree(
            branch=req.branch,
            description=req.description,
            plan_path=req.plan_path,
            base_branch=req.base_branch,
        )
        return DevCreateWorktreeResponse(ok=True, worktree=_worktree_to_response(wt))
    except ValueError as e:
        return DevCreateWorktreeResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to create worktree")
        return DevCreateWorktreeResponse(ok=False, error=str(e))


@router.post("/api/dev/worktrees/{worktree_id}/start", response_model=DevStartServicesResponse)
def start_worktree_services(
    worktree_id: str, req: DevStartServicesRequest, worktree_manager: WorktreeManagerDep
) -> DevStartServicesResponse:
    try:
        status = worktree_manager.start_services(
            worktree_id=worktree_id,
            backend_port=req.backend_port,
            frontend_port=req.frontend_port,
        )
        return DevStartServicesResponse(
            ok=True,
            services=DevServiceStatus(
                backend=DevServiceState(
                    running=status.backend.running,
                    port=status.backend.port,
                    pid=status.backend.pid,
                    url=status.backend.url,
                ),
                frontend=DevServiceState(
                    running=status.frontend.running,
                    port=status.frontend.port,
                    pid=status.frontend.pid,
                    url=status.frontend.url,
                ),
            ),
        )
    except ValueError as e:
        return DevStartServicesResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to start services")
        return DevStartServicesResponse(ok=False, error=str(e))


@router.post("/api/dev/worktrees/{worktree_id}/stop", response_model=DevStopServicesResponse)
def stop_worktree_services(worktree_id: str, worktree_manager: WorktreeManagerDep) -> DevStopServicesResponse:
    try:
        ok = worktree_manager.stop_services(worktree_id)
        return DevStopServicesResponse(ok=ok)
    except Exception as e:
        logger.exception("Failed to stop services")
        return DevStopServicesResponse(ok=False, error=str(e))


@router.delete("/api/dev/worktrees/{worktree_id}", response_model=DevDeleteWorktreeResponse)
def delete_worktree(
    worktree_id: str,
    req: DevDeleteWorktreeRequest,
    worktree_manager: WorktreeManagerDep,
) -> DevDeleteWorktreeResponse:
    try:
        ok = worktree_manager.delete_worktree(worktree_id, force=req.force)
        return DevDeleteWorktreeResponse(ok=ok)
    except ValueError as e:
        return DevDeleteWorktreeResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to delete worktree")
        return DevDeleteWorktreeResponse(ok=False, error=str(e))


@router.get("/api/dev/ports/allocate", response_model=DevPortAllocationResponse)
def allocate_ports_endpoint(worktree_manager: WorktreeManagerDep) -> DevPortAllocationResponse:
    from .port_allocator import allocate_ports as do_allocate

    index = worktree_manager.read_index()
    used_backend = {v.get("backend_port", 0) for v in index.get("allocations", {}).values()}
    used_frontend = {v.get("frontend_port", 0) for v in index.get("allocations", {}).values()}
    backend_port, frontend_port = do_allocate(used_backend, used_frontend)
    return DevPortAllocationResponse(backend_port=backend_port, frontend_port=frontend_port)


@router.patch("/api/dev/worktrees/{worktree_id}/metadata", response_model=DevUpdateMetadataResponse)
def update_worktree_metadata(
    worktree_id: str,
    req: DevUpdateMetadataRequest,
    worktree_manager: WorktreeManagerDep,
) -> DevUpdateMetadataResponse:
    try:
        metadata = worktree_manager.update_metadata(
            worktree_id=worktree_id,
            description=req.description,
            plan_path=req.plan_path,
        )
        if metadata is None:
            return DevUpdateMetadataResponse(ok=False, error="worktree_not_found")
        return DevUpdateMetadataResponse(
            ok=True,
            metadata=DevWorktreeMetadata(
                description=metadata.description,
                plan_path=metadata.plan_path,
                created_at=metadata.created_at,
                owner=metadata.owner,
                ports=metadata.ports,
            ),
        )
    except Exception as e:
        logger.exception("Failed to update metadata")
        return DevUpdateMetadataResponse(ok=False, error=str(e))


@router.post("/api/dev/market/ingest/candles_closed_batch", response_model=IngestCandlesClosedBatchResponse)
async def ingest_candles_closed_batch(
    req: IngestCandlesClosedBatchRequest,
    ingest_service: MarketIngestServiceDep,
) -> IngestCandlesClosedBatchResponse:
    try:
        return await ingest_service.ingest_candles_closed_batch(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_dev_routes(app: FastAPI) -> None:
    app.include_router(router)
