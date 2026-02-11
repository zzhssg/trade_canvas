from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .factor_store import FactorEventRow, FactorStore
from .overlay_renderer_bucketing import collect_overlay_event_buckets
from .store import CandleStore


@dataclass(frozen=True)
class OverlayIngestInput:
    to_time: int
    cutoff_time: int
    window_candles: int
    factor_rows: list[FactorEventRow]
    buckets: dict[str, list[dict[str, Any]]]
    candles: list[Any]


class OverlayIngestReader:
    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        event_bucket_by_kind: dict[tuple[str, str], str],
        event_bucket_sort_keys: dict[str, tuple[str, str]],
        event_bucket_names: tuple[str, ...],
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._event_bucket_by_kind = event_bucket_by_kind
        self._event_bucket_sort_keys = event_bucket_sort_keys
        self._event_bucket_names = event_bucket_names

    def read(
        self,
        *,
        series_id: str,
        to_time: int,
        tf_s: int,
        window_candles: int,
    ) -> OverlayIngestInput:
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))
        factor_rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(cutoff_time),
            end_candle_time=int(to_time),
            limit=50000,
        )
        buckets = collect_overlay_event_buckets(
            rows=factor_rows,
            event_bucket_by_kind=self._event_bucket_by_kind,
            event_bucket_sort_keys=self._event_bucket_sort_keys,
            event_bucket_names=self._event_bucket_names,
        )
        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(cutoff_time),
            end_time=int(to_time),
            limit=int(window_candles) + 10,
        )
        return OverlayIngestInput(
            to_time=int(to_time),
            cutoff_time=int(cutoff_time),
            window_candles=int(window_candles),
            factor_rows=factor_rows,
            buckets=buckets,
            candles=candles,
        )
