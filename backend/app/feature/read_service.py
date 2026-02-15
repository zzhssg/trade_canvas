from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..core.ports import AlignedStorePort, HeadStorePort
from ..core.service_errors import ServiceError
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds
from .contracts import (
    FeatureColumnSpec,
    FeatureVectorBatchV1,
    FeatureVectorRowV1,
    normalize_feature_row_values,
    validate_feature_columns,
)
from .store import FeatureVectorRow


class FeatureStoreReadPort(HeadStorePort, Protocol):
    def get_rows_between_times(
        self,
        *,
        series_id: str,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list[FeatureVectorRow]: ...


@dataclass(frozen=True)
class FeatureReadService:
    store: AlignedStorePort
    feature_store: FeatureStoreReadPort
    strict_mode: bool = True

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

    def _ensure_strict_freshness(self, *, series_id: str, aligned_time: int | None) -> None:
        if aligned_time is None or int(aligned_time) <= 0:
            return
        feature_head = self.feature_store.head_time(series_id)
        if feature_head is None or int(feature_head) < int(aligned_time):
            raise ServiceError(
                status_code=409,
                detail="ledger_out_of_sync:feature",
                code="feature_read.ledger_out_of_sync",
            )

    @staticmethod
    def _infer_source_factor(key: str) -> str:
        name = str(key or "").strip()
        if not name:
            return "feature"
        if name.endswith("_event_count"):
            source = name[: -len("_event_count")]
            return source or "feature"
        if "_" not in name:
            return "feature"
        source, _ = name.split("_", 1)
        return source or "feature"

    @staticmethod
    def _infer_value_type(value: Any) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        return "float"

    def _build_columns(self, *, rows: list[FeatureVectorRow]) -> tuple[FeatureColumnSpec, ...]:
        value_types: dict[str, str] = {}
        ordered_keys: list[str] = []
        for row in rows:
            for key, value in (row.values or {}).items():
                name = str(key)
                if name not in value_types:
                    ordered_keys.append(name)
                    value_types[name] = "float"
                if value is None:
                    continue
                value_types[name] = self._infer_value_type(value)

        columns = tuple(
            FeatureColumnSpec(
                key=name,
                source_factor=self._infer_source_factor(name),
                value_type=value_types.get(name, "float"),
                nullable=True,
            )
            for name in ordered_keys
        )
        return validate_feature_columns(columns)

    @staticmethod
    def _resolve_window_start(*, aligned_time: int, window_candles: int, series_id: str) -> int:
        timeframe = series_id_timeframe(series_id)
        timeframe_seconds = max(1, int(timeframe_to_seconds(timeframe)))
        window = max(1, int(window_candles))
        return max(0, int(aligned_time) - window * timeframe_seconds)

    def read_batch(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
        limit: int = 20000,
    ) -> FeatureVectorBatchV1:
        aligned = self.resolve_aligned_time(
            series_id=series_id,
            at_time=int(at_time),
            aligned_time=aligned_time,
        )
        if bool(self.strict_mode) and bool(ensure_fresh):
            self._ensure_strict_freshness(series_id=series_id, aligned_time=aligned)
        if aligned is None:
            return FeatureVectorBatchV1(
                series_id=str(series_id),
                aligned_time=0,
                columns=tuple(),
                rows=tuple(),
            )

        start_time = self._resolve_window_start(
            aligned_time=int(aligned),
            window_candles=int(window_candles),
            series_id=series_id,
        )
        read_limit = max(1, int(limit))
        rows = self.feature_store.get_rows_between_times(
            series_id=series_id,
            start_candle_time=int(start_time),
            end_candle_time=int(aligned),
            limit=int(read_limit),
        )
        columns = self._build_columns(rows=rows)
        out_rows: list[FeatureVectorRowV1] = []
        for row in rows:
            out_rows.append(
                FeatureVectorRowV1(
                    series_id=str(row.series_id),
                    candle_time=int(row.candle_time),
                    candle_id=str(row.candle_id),
                    values=normalize_feature_row_values(columns=columns, values=dict(row.values or {})),
                )
            )

        return FeatureVectorBatchV1(
            series_id=str(series_id),
            aligned_time=int(aligned),
            columns=columns,
            rows=tuple(out_rows),
        )
