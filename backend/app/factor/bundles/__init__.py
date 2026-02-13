from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType
from typing import cast

from ..graph import FactorGraph, FactorSpec
from ..registry import FactorPlugin
from ..slice_plugin_contract import FactorSlicePlugin

BundleBuilders = tuple[
    Callable[[], FactorPlugin],
    Callable[[], FactorSlicePlugin],
]

_BUILD_BUNDLE_ATTR = "build_bundle"


class FactorBundleDiscoveryError(RuntimeError):
    pass


def _iter_bundle_module_names() -> tuple[str, ...]:
    names: list[str] = []
    for module_info in pkgutil.iter_modules(__path__):
        name = str(module_info.name)
        if name.startswith("_"):
            continue
        if name == "common":
            continue
        names.append(name)
    if not names:
        raise FactorBundleDiscoveryError("factor_bundle_discovery_empty")
    names.sort()
    return tuple(names)


def _load_module(module_name: str) -> ModuleType:
    qualified_name = f"{__name__}.{module_name}"
    try:
        return importlib.import_module(qualified_name)
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise FactorBundleDiscoveryError(f"factor_bundle_import_failed:{qualified_name}:{exc}") from exc


def _load_builders(module_name: str) -> BundleBuilders:
    module = _load_module(module_name)
    factory = getattr(module, _BUILD_BUNDLE_ATTR, None)
    if not callable(factory):
        raise FactorBundleDiscoveryError(f"factor_bundle_missing_factory:{module.__name__}")
    try:
        raw = factory()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise FactorBundleDiscoveryError(f"factor_bundle_factory_failed:{module.__name__}:{exc}") from exc

    if not isinstance(raw, tuple) or len(raw) != 2:
        raise FactorBundleDiscoveryError(f"factor_bundle_factory_invalid_return:{module.__name__}")

    tick_builder, slice_builder = cast(BundleBuilders, raw)
    if not callable(tick_builder) or not callable(slice_builder):
        raise FactorBundleDiscoveryError(f"factor_bundle_factory_non_callable:{module.__name__}")
    return tick_builder, slice_builder


def _instantiate_plugins(*, module_name: str, builders: BundleBuilders) -> tuple[FactorPlugin, FactorSlicePlugin]:
    tick_builder, slice_builder = builders
    try:
        tick_plugin = tick_builder()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise FactorBundleDiscoveryError(f"factor_bundle_tick_build_failed:{module_name}:{exc}") from exc

    try:
        slice_plugin = slice_builder()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise FactorBundleDiscoveryError(f"factor_bundle_slice_build_failed:{module_name}:{exc}") from exc

    return tick_plugin, slice_plugin


def build_default_factor_bundles() -> tuple[BundleBuilders, ...]:
    builders_by_factor: dict[str, BundleBuilders] = {}
    graph_specs: list[FactorSpec] = []

    for module_name in _iter_bundle_module_names():
        builders = _load_builders(module_name)
        tick_plugin, slice_plugin = _instantiate_plugins(module_name=module_name, builders=builders)

        tick_name = str(tick_plugin.spec.factor_name or "").strip()
        slice_name = str(slice_plugin.spec.factor_name or "").strip()
        if not tick_name:
            raise FactorBundleDiscoveryError(f"factor_bundle_empty_tick_name:{module_name}")
        if tick_name != slice_name:
            raise FactorBundleDiscoveryError(
                f"factor_bundle_mismatch:{module_name}:tick={tick_name}:slice={slice_name}"
            )

        tick_depends_on = tuple(tick_plugin.spec.depends_on)
        slice_depends_on = tuple(slice_plugin.spec.depends_on)
        if tick_depends_on != slice_depends_on:
            raise FactorBundleDiscoveryError(
                f"factor_bundle_depends_on_mismatch:{tick_name}:tick={tick_depends_on}:slice={slice_depends_on}"
            )

        if tick_name in builders_by_factor:
            raise FactorBundleDiscoveryError(f"factor_bundle_duplicate:{tick_name}")

        builders_by_factor[tick_name] = builders
        graph_specs.append(FactorSpec(factor_name=tick_name, depends_on=tick_depends_on))

    try:
        graph = FactorGraph(graph_specs)
    except Exception as exc:
        raise FactorBundleDiscoveryError(f"factor_bundle_graph_invalid:{exc}") from exc

    return tuple(builders_by_factor[factor_name] for factor_name in graph.topo_order)


__all__ = [
    "BundleBuilders",
    "FactorBundleDiscoveryError",
    "build_default_factor_bundles",
]
