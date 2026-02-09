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
