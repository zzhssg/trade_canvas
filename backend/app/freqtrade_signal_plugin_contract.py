from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .factor_plugin_contract import FactorPluginSpec


@dataclass(frozen=True)
class FreqtradeSignalBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


@dataclass(frozen=True)
class FreqtradeSignalContext:
    series_id: str
    timeframe: str
    dataframe: Any
    order: list[Any]
    times_by_index: Mapping[Any, int]
    buckets: Mapping[str, list[dict[str, Any]]]


class FreqtradeSignalPlugin(Protocol):
    @property
    def spec(self) -> FactorPluginSpec: ...

    @property
    def bucket_specs(self) -> tuple[FreqtradeSignalBucketSpec, ...]: ...

    def prepare_dataframe(self, *, dataframe: Any) -> None: ...

    def apply(self, *, ctx: FreqtradeSignalContext) -> None: ...
