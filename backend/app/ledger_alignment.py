from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .service_errors import ServiceError


class AlignedStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class HeadStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


@dataclass(frozen=True)
class LedgerAlignedPoint:
    requested_time: int
    aligned_time: int


@dataclass(frozen=True)
class LedgerHeadTimes:
    factor_head_time: int
    overlay_head_time: int


def require_aligned_point(
    *,
    store: AlignedStoreLike,
    series_id: str,
    to_time: int | None,
    no_data_code: str,
    no_data_detail: str = "no_data",
) -> LedgerAlignedPoint:
    store_head = store.head_time(series_id)
    if store_head is None:
        raise ServiceError(status_code=404, detail=no_data_detail, code=no_data_code)

    requested_time = int(to_time) if to_time is not None else int(store_head)
    aligned_time = store.floor_time(series_id, at_time=int(requested_time))
    if aligned_time is None:
        raise ServiceError(status_code=404, detail=no_data_detail, code=no_data_code)

    return LedgerAlignedPoint(requested_time=int(requested_time), aligned_time=int(aligned_time))


def require_ledger_heads_ready(
    *,
    factor_store: HeadStoreLike,
    overlay_store: HeadStoreLike,
    series_id: str,
    aligned_time: int,
    factor_out_of_sync_code: str,
    overlay_out_of_sync_code: str,
    factor_out_of_sync_detail: str = "ledger_out_of_sync:factor",
    overlay_out_of_sync_detail: str = "ledger_out_of_sync:overlay",
) -> LedgerHeadTimes:
    factor_head = factor_store.head_time(series_id)
    if factor_head is None or int(factor_head) < int(aligned_time):
        raise ServiceError(
            status_code=409,
            detail=factor_out_of_sync_detail,
            code=factor_out_of_sync_code,
        )

    overlay_head = overlay_store.head_time(series_id)
    if overlay_head is None or int(overlay_head) < int(aligned_time):
        raise ServiceError(
            status_code=409,
            detail=overlay_out_of_sync_detail,
            code=overlay_out_of_sync_code,
        )

    return LedgerHeadTimes(
        factor_head_time=int(factor_head),
        overlay_head_time=int(overlay_head),
    )
