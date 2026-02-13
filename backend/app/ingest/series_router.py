from __future__ import annotations

from dataclasses import dataclass

from ..derived_timeframes import is_derived_series_id_with_config, to_base_series_id_with_base
from .source_registry import IngestSourceBinding, IngestSourceRegistry
from ..series_id import parse_series_id


@dataclass(frozen=True)
class IngestSeriesRouterConfig:
    derived_enabled: bool
    derived_base_timeframe: str
    derived_timeframes: tuple[str, ...]


class IngestSeriesRouter:
    def __init__(
        self,
        *,
        source_registry: IngestSourceRegistry,
        config: IngestSeriesRouterConfig,
    ) -> None:
        self._source_registry = source_registry
        self._config = config

    def normalize(self, series_id: str) -> str:
        config = self._config
        if not is_derived_series_id_with_config(
            series_id,
            enabled=bool(config.derived_enabled),
            base_timeframe=str(config.derived_base_timeframe),
            derived=tuple(config.derived_timeframes),
        ):
            return series_id
        return to_base_series_id_with_base(
            series_id,
            base_timeframe=str(config.derived_base_timeframe),
        )

    def resolve_source(self, *, series_id: str) -> IngestSourceBinding:
        exchange = parse_series_id(series_id).exchange
        return self._source_registry.resolve(exchange=exchange)
