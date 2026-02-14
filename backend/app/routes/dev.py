from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from ..deps import ApiGatesDep, MarketIngestServiceDep, WorktreeManagerDep
from ..core import schemas as core_schemas
from ..core.service_errors import ServiceError, to_http_exception


def _require_dev_api_enabled(api_gates: ApiGatesDep) -> None:
    if not api_gates.dev_api:
        raise HTTPException(status_code=404, detail="not_found")


router = APIRouter(dependencies=[Depends(_require_dev_api_enabled)])
logger = logging.getLogger(__name__)


def _worktree_to_response(wt) -> core_schemas.DevWorktreeInfo:
    metadata = None
    if wt.metadata:
        metadata = core_schemas.DevWorktreeMetadata(
            description=wt.metadata.description,
            plan_path=wt.metadata.plan_path,
            created_at=wt.metadata.created_at,
            owner=wt.metadata.owner,
            ports=wt.metadata.ports,
        )
    services = None
    if wt.services:
        services = core_schemas.DevServiceStatus(
            backend=core_schemas.DevServiceState(
                running=wt.services.backend.running,
                port=wt.services.backend.port,
                pid=wt.services.backend.pid,
                url=wt.services.backend.url,
            ),
            frontend=core_schemas.DevServiceState(
                running=wt.services.frontend.running,
                port=wt.services.frontend.port,
                pid=wt.services.frontend.pid,
                url=wt.services.frontend.url,
            ),
        )
    return core_schemas.DevWorktreeInfo(
        id=wt.id,
        path=wt.path,
        branch=wt.branch,
        commit=wt.commit,
        is_detached=wt.is_detached,
        is_main=wt.is_main,
        metadata=metadata,
        services=services,
    )


@router.get("/api/dev/worktrees", response_model=core_schemas.DevWorktreeListResponse)
def list_worktrees(worktree_manager: WorktreeManagerDep) -> core_schemas.DevWorktreeListResponse:
    worktrees = worktree_manager.list_worktrees()
    return core_schemas.DevWorktreeListResponse(worktrees=[_worktree_to_response(wt) for wt in worktrees])


@router.get("/api/dev/worktrees/{worktree_id}", response_model=core_schemas.DevWorktreeInfo)
def get_worktree(worktree_id: str, worktree_manager: WorktreeManagerDep) -> core_schemas.DevWorktreeInfo:
    wt = worktree_manager.get_worktree(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree_not_found")
    return _worktree_to_response(wt)


@router.post("/api/dev/worktrees", response_model=core_schemas.DevCreateWorktreeResponse)
def create_worktree(
    req: core_schemas.DevCreateWorktreeRequest, worktree_manager: WorktreeManagerDep
) -> core_schemas.DevCreateWorktreeResponse:
    try:
        wt = worktree_manager.create_worktree(
            branch=req.branch,
            description=req.description,
            plan_path=req.plan_path,
            base_branch=req.base_branch,
        )
        return core_schemas.DevCreateWorktreeResponse(ok=True, worktree=_worktree_to_response(wt))
    except ValueError as e:
        return core_schemas.DevCreateWorktreeResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to create worktree")
        return core_schemas.DevCreateWorktreeResponse(ok=False, error=str(e))


@router.post("/api/dev/worktrees/{worktree_id}/start", response_model=core_schemas.DevStartServicesResponse)
def start_worktree_services(
    worktree_id: str, req: core_schemas.DevStartServicesRequest, worktree_manager: WorktreeManagerDep
) -> core_schemas.DevStartServicesResponse:
    try:
        status = worktree_manager.start_services(
            worktree_id=worktree_id,
            backend_port=req.backend_port,
            frontend_port=req.frontend_port,
        )
        return core_schemas.DevStartServicesResponse(
            ok=True,
            services=core_schemas.DevServiceStatus(
                backend=core_schemas.DevServiceState(
                    running=status.backend.running,
                    port=status.backend.port,
                    pid=status.backend.pid,
                    url=status.backend.url,
                ),
                frontend=core_schemas.DevServiceState(
                    running=status.frontend.running,
                    port=status.frontend.port,
                    pid=status.frontend.pid,
                    url=status.frontend.url,
                ),
            ),
        )
    except ValueError as e:
        return core_schemas.DevStartServicesResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to start services")
        return core_schemas.DevStartServicesResponse(ok=False, error=str(e))


@router.post("/api/dev/worktrees/{worktree_id}/stop", response_model=core_schemas.DevStopServicesResponse)
def stop_worktree_services(worktree_id: str, worktree_manager: WorktreeManagerDep) -> core_schemas.DevStopServicesResponse:
    try:
        ok = worktree_manager.stop_services(worktree_id)
        return core_schemas.DevStopServicesResponse(ok=ok)
    except Exception as e:
        logger.exception("Failed to stop services")
        return core_schemas.DevStopServicesResponse(ok=False, error=str(e))


@router.delete("/api/dev/worktrees/{worktree_id}", response_model=core_schemas.DevDeleteWorktreeResponse)
def delete_worktree(
    worktree_id: str,
    req: core_schemas.DevDeleteWorktreeRequest,
    worktree_manager: WorktreeManagerDep,
) -> core_schemas.DevDeleteWorktreeResponse:
    try:
        ok = worktree_manager.delete_worktree(worktree_id, force=req.force)
        return core_schemas.DevDeleteWorktreeResponse(ok=ok)
    except ValueError as e:
        return core_schemas.DevDeleteWorktreeResponse(ok=False, error=str(e))
    except Exception as e:
        logger.exception("Failed to delete worktree")
        return core_schemas.DevDeleteWorktreeResponse(ok=False, error=str(e))


@router.get("/api/dev/ports/allocate", response_model=core_schemas.DevPortAllocationResponse)
def allocate_ports_endpoint(worktree_manager: WorktreeManagerDep) -> core_schemas.DevPortAllocationResponse:
    from ..worktree.port_allocator import allocate_ports as do_allocate

    index = worktree_manager.read_index()
    used_backend = {v.get("backend_port", 0) for v in index.get("allocations", {}).values()}
    used_frontend = {v.get("frontend_port", 0) for v in index.get("allocations", {}).values()}
    backend_port, frontend_port = do_allocate(used_backend, used_frontend)
    return core_schemas.DevPortAllocationResponse(backend_port=backend_port, frontend_port=frontend_port)


@router.patch("/api/dev/worktrees/{worktree_id}/metadata", response_model=core_schemas.DevUpdateMetadataResponse)
def update_worktree_metadata(
    worktree_id: str,
    req: core_schemas.DevUpdateMetadataRequest,
    worktree_manager: WorktreeManagerDep,
) -> core_schemas.DevUpdateMetadataResponse:
    try:
        metadata = worktree_manager.update_metadata(
            worktree_id=worktree_id,
            description=req.description,
            plan_path=req.plan_path,
        )
        if metadata is None:
            return core_schemas.DevUpdateMetadataResponse(ok=False, error="worktree_not_found")
        return core_schemas.DevUpdateMetadataResponse(
            ok=True,
            metadata=core_schemas.DevWorktreeMetadata(
                description=metadata.description,
                plan_path=metadata.plan_path,
                created_at=metadata.created_at,
                owner=metadata.owner,
                ports=metadata.ports,
            ),
        )
    except Exception as e:
        logger.exception("Failed to update metadata")
        return core_schemas.DevUpdateMetadataResponse(ok=False, error=str(e))


@router.post("/api/dev/market/ingest/candles_closed_batch", response_model=core_schemas.IngestCandlesClosedBatchResponse)
async def ingest_candles_closed_batch(
    req: core_schemas.IngestCandlesClosedBatchRequest,
    ingest_service: MarketIngestServiceDep,
) -> core_schemas.IngestCandlesClosedBatchResponse:
    try:
        return await ingest_service.ingest_candles_closed_batch(req)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_dev_routes(app: FastAPI) -> None:
    app.include_router(router)
