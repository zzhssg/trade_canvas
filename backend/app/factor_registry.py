from __future__ import annotations

from typing import cast

from .factor_plugin_contract import FactorPluginSpec, FactorTickPlugin
from .factor_plugin_registry import FactorPluginRegistry, FactorPluginRegistryError

FactorPlugin = FactorTickPlugin
PluginSpec = FactorPluginSpec

FactorRegistryError = FactorPluginRegistryError


class FactorRegistry(FactorPluginRegistry):
    def tick_plugins(self) -> tuple[FactorPlugin, ...]:
        return tuple(cast(FactorPlugin, plugin) for plugin in self.plugins())
