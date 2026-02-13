from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .plugin_contract import FactorPluginSpec
from .store import FactorHeadSnapshotRow
from ..schemas import FactorSliceV1
from ..store import CandleStore


@dataclass(frozen=True)
class SliceBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


@dataclass(frozen=True)
class FactorSliceBuildContext:
    series_id: str
    aligned_time: int
    at_time: int
    start_time: int
    window_candles: int
    candle_id: str
    candle_store: CandleStore
    buckets: Mapping[str, list[dict[str, Any]]]
    head_rows: Mapping[str, FactorHeadSnapshotRow | None]
    snapshots: Mapping[str, FactorSliceV1]


class FactorSlicePlugin(Protocol):
    @property
    def spec(self) -> FactorPluginSpec: ...

    @property
    def bucket_specs(self) -> tuple[SliceBucketSpec, ...]: ...

    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None: ...
