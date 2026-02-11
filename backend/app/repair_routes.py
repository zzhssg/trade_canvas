from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException

from .dependencies import ReadRepairServiceDep, RuntimeFlagsDep
from .schemas import RepairOverlayRequestV1, RepairOverlayResponseV1
from .service_errors import ServiceError, to_http_exception

router = APIRouter()


@router.post("/api/dev/repair/overlay", response_model=RepairOverlayResponseV1)
def repair_overlay_ledger(
    payload: RepairOverlayRequestV1,
    *,
    runtime_flags: RuntimeFlagsDep,
    repair_service: ReadRepairServiceDep,
) -> RepairOverlayResponseV1:
    if not bool(runtime_flags.enable_dev_api):
        raise HTTPException(status_code=404, detail="not_found")
    if not bool(runtime_flags.enable_read_repair_api):
        raise HTTPException(status_code=404, detail="not_found")
    try:
        return repair_service.repair_overlay(payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_repair_routes(app: FastAPI) -> None:
    app.include_router(router)
