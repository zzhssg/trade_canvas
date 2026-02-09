from __future__ import annotations

from typing import Any


def ensure_factor_fresh_for_read(*, factor_orchestrator: Any, series_id: str, up_to_time: int | None) -> bool:
    if up_to_time is None:
        return False
    to_time = int(up_to_time)
    if to_time <= 0:
        return False
    result = factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=to_time)
    return bool(getattr(result, "rebuilt", False))


def read_factor_slices_with_freshness(
    *,
    store: Any,
    factor_orchestrator: Any,
    factor_slices_service: Any,
    series_id: str,
    at_time: int,
    window_candles: int,
    aligned_time: int | None = None,
    ensure_fresh: bool = True,
) -> Any:
    aligned: int | None
    if aligned_time is None:
        aligned = store.floor_time(series_id, at_time=int(at_time))
    else:
        aligned = int(aligned_time)
        if aligned <= 0:
            aligned = None
    if bool(ensure_fresh):
        _ = ensure_factor_fresh_for_read(
            factor_orchestrator=factor_orchestrator,
            series_id=series_id,
            up_to_time=aligned,
        )
    return factor_slices_service.get_slices_aligned(
        series_id=series_id,
        aligned_time=aligned,
        at_time=int(at_time),
        window_candles=int(window_candles),
    )
