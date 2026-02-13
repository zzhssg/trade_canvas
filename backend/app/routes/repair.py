from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException

from ..deps import ApiGatesDep, ReadRepairServiceDep
from ..core.schemas import RepairOverlayRequestV1, RepairOverlayResponseV1
from ..core.service_errors import ServiceError, to_http_exception

router = APIRouter()


@router.post("/api/dev/repair/overlay", response_model=RepairOverlayResponseV1)
def repair_overlay_ledger(
    payload: RepairOverlayRequestV1,
    *,
    api_gates: ApiGatesDep,
    repair_service: ReadRepairServiceDep,
) -> RepairOverlayResponseV1:
    if not api_gates.dev_api:
        raise HTTPException(status_code=404, detail="not_found")
    if not api_gates.read_repair_api:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        return repair_service.repair_overlay(payload)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc


def register_repair_routes(app: FastAPI) -> None:
    app.include_router(router)
