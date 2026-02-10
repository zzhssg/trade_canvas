from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .factor_runtime_contract import FactorRuntimeContext


@dataclass(frozen=True)
class FactorCatalogSubFeatureSpec:
    key: str
    label: str
    default_visible: bool = True


@dataclass(frozen=True)
class FactorCatalogSpec:
    label: str | None = None
    default_visible: bool = True
    sub_features: tuple[FactorCatalogSubFeatureSpec, ...] = ()


@dataclass(frozen=True)
class FactorPluginSpec:
    """
    Runtime plugin identity and dependency declaration.

    - factor_name: stable plugin key (also used as ledger factor_name)
    - depends_on: upstream plugin keys required by this plugin
    - catalog: frontend factor panel metadata (optional)
    """

    factor_name: str
    depends_on: tuple[str, ...] = ()
    catalog: FactorCatalogSpec | None = None


class FactorPlugin(Protocol):
    @property
    def spec(self) -> FactorPluginSpec: ...


class FactorTickPlugin(FactorPlugin, Protocol):
    def run_tick(self, *, series_id: str, state: Any, runtime: FactorRuntimeContext) -> None: ...


class FactorBootstrapPlugin(FactorTickPlugin, Protocol):
    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None: ...

    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None: ...

    def bootstrap_from_history(self, *, series_id: str, state: Any, runtime: FactorRuntimeContext) -> None: ...


class FactorHeadSnapshotPlugin(FactorTickPlugin, Protocol):
    def build_head_snapshot(
        self,
        *,
        series_id: str,
        state: Any,
        runtime: FactorRuntimeContext,
    ) -> dict[str, Any] | None: ...
