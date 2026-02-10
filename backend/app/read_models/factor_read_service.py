from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from ..factor_read_freshness import ensure_factor_fresh_for_read


@dataclass(frozen=True)
class FactorReadService:
    store: Any
    factor_store: Any
    factor_orchestrator: Any
    factor_slices_service: Any
    strict_mode: bool = False

    def resolve_aligned_time(
        self,
        *,
        series_id: str,
        at_time: int,
        aligned_time: int | None = None,
    ) -> int | None:
        if aligned_time is not None:
            candidate = int(aligned_time)
            return candidate if candidate > 0 else None
        return self.store.floor_time(series_id, at_time=int(at_time))

    def _factor_head_time(self, *, series_id: str) -> int | None:
        try:
            head = self.factor_store.head_time(series_id)
        except Exception:
            return None
        if head is None:
            return None
        return int(head)

    def _ensure_strict_freshness(self, *, series_id: str, aligned_time: int | None) -> None:
        if aligned_time is None or int(aligned_time) <= 0:
            return
        factor_head = self._factor_head_time(series_id=series_id)
        if factor_head is None or int(factor_head) < int(aligned_time):
            raise HTTPException(status_code=409, detail="ledger_out_of_sync:factor")

    def read_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
    ) -> Any:
        aligned = self.resolve_aligned_time(
            series_id=series_id,
            at_time=int(at_time),
            aligned_time=aligned_time,
        )
        if bool(ensure_fresh):
            if self.strict_mode:
                self._ensure_strict_freshness(series_id=series_id, aligned_time=aligned)
            else:
                _ = ensure_factor_fresh_for_read(
                    factor_orchestrator=self.factor_orchestrator,
                    series_id=series_id,
                    up_to_time=aligned,
                )
        return self.factor_slices_service.get_slices_aligned(
            series_id=series_id,
            aligned_time=aligned,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )
