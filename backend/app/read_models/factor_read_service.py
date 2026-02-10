from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor_read_freshness import read_factor_slices_with_freshness


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
        return read_factor_slices_with_freshness(
            store=self.store,
            factor_orchestrator=self.factor_orchestrator,
            factor_slices_service=self.factor_slices_service,
            series_id=series_id,
            at_time=int(at_time),
            window_candles=int(window_candles),
            aligned_time=aligned,
            ensure_fresh=bool(ensure_fresh),
            strict_mode=bool(self.strict_mode),
            factor_store=self.factor_store,
        )
