from __future__ import annotations

from typing import Protocol

from ..core.ports import AlignedStorePort, HeadStorePort
from ..core.schemas import GetFactorSlicesResponseV1
from ..core.service_errors import ServiceError


class FactorSlicesServicePort(Protocol):
    def get_slices_aligned(
        self,
        *,
        series_id: str,
        aligned_time: int | None,
        at_time: int,
        window_candles: int,
    ) -> GetFactorSlicesResponseV1: ...


def _factor_head_time(
    *,
    factor_store: HeadStorePort | None,
    factor_slices_service: FactorSlicesServicePort,
    series_id: str,
) -> int | None:
    try:
        store = factor_store
        if store is None:
            store = getattr(factor_slices_service, "factor_store", None)
        if store is None:
            return None
        head = store.head_time(series_id)
    except Exception:
        return None
    if head is None:
        return None
    try:
        return int(head)
    except (ValueError, TypeError):
        return None


def _ensure_strict_freshness(
    *,
    factor_store: HeadStorePort | None,
    factor_slices_service: FactorSlicesServicePort,
    series_id: str,
    aligned_time: int | None,
) -> None:
    if aligned_time is None or int(aligned_time) <= 0:
        return
    factor_head = _factor_head_time(
        factor_store=factor_store,
        factor_slices_service=factor_slices_service,
        series_id=series_id,
    )
    if factor_head is None or int(factor_head) < int(aligned_time):
        raise ServiceError(
            status_code=409,
            detail="ledger_out_of_sync:factor",
            code="factor_read.ledger_out_of_sync",
        )


def read_factor_slices_with_freshness(
    *,
    store: AlignedStorePort,
    factor_slices_service: FactorSlicesServicePort,
    series_id: str,
    at_time: int,
    window_candles: int,
    aligned_time: int | None = None,
    ensure_fresh: bool = True,
    factor_store: HeadStorePort | None = None,
) -> GetFactorSlicesResponseV1:
    aligned: int | None
    if aligned_time is None:
        aligned = store.floor_time(series_id, at_time=int(at_time))
    else:
        aligned = int(aligned_time)
        if aligned <= 0:
            aligned = None
    if bool(ensure_fresh):
        _ensure_strict_freshness(
            factor_store=factor_store,
            factor_slices_service=factor_slices_service,
            series_id=series_id,
            aligned_time=aligned,
        )
    return factor_slices_service.get_slices_aligned(
        series_id=series_id,
        aligned_time=aligned,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )
