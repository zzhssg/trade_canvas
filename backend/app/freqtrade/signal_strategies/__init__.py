from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from ...factor.graph import FactorGraph, FactorSpec
from ..signal_plugin_contract import FreqtradeSignalPlugin

_BUILD_SIGNAL_PLUGIN_ATTR = "build_signal_plugin"


class SignalPluginDiscoveryError(RuntimeError):
    pass


def _iter_strategy_module_names() -> tuple[str, ...]:
    names: list[str] = []
    for module_info in pkgutil.iter_modules(__path__):
        module_name = str(module_info.name)
        if module_name.startswith("_"):
            continue
        names.append(module_name)
    if not names:
        raise SignalPluginDiscoveryError("signal_plugin_discovery_empty")
    names.sort()
    return tuple(names)


def _import_module(module_name: str) -> ModuleType:
    qualified_name = f"{__name__}.{module_name}"
    try:
        return importlib.import_module(qualified_name)
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise SignalPluginDiscoveryError(f"signal_plugin_import_failed:{qualified_name}:{exc}") from exc


def _build_plugin_from_module(module_name: str) -> FreqtradeSignalPlugin:
    module = _import_module(module_name)
    factory = getattr(module, _BUILD_SIGNAL_PLUGIN_ATTR, None)
    if not callable(factory):
        raise SignalPluginDiscoveryError(f"signal_plugin_missing_factory:{module.__name__}")
    try:
        plugin = factory()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise SignalPluginDiscoveryError(f"signal_plugin_factory_failed:{module.__name__}:{exc}") from exc
    return plugin


def build_default_freqtrade_signal_plugins() -> tuple[FreqtradeSignalPlugin, ...]:
    plugins_by_name: dict[str, FreqtradeSignalPlugin] = {}
    specs: list[FactorSpec] = []

    for module_name in _iter_strategy_module_names():
        plugin = _build_plugin_from_module(module_name)
        plugin_name = str(plugin.spec.factor_name or "").strip()
        if not plugin_name:
            raise SignalPluginDiscoveryError(f"signal_plugin_empty_name:{module_name}")
        if plugin_name in plugins_by_name:
            raise SignalPluginDiscoveryError(f"signal_plugin_duplicate:{plugin_name}")

        depends_on = tuple(plugin.spec.depends_on)
        plugins_by_name[plugin_name] = plugin
        specs.append(FactorSpec(factor_name=plugin_name, depends_on=depends_on))

    try:
        graph = FactorGraph(specs)
    except Exception as exc:
        raise SignalPluginDiscoveryError(f"signal_plugin_graph_invalid:{exc}") from exc

    return tuple(plugins_by_name[name] for name in graph.topo_order)


__all__ = [
    "SignalPluginDiscoveryError",
    "build_default_freqtrade_signal_plugins",
]
