from __future__ import annotations

from typing import cast

from .factor_plugin_contract import FactorPluginSpec, FactorTickPlugin
from .factor_plugin_registry import FactorPluginRegistry, FactorPluginRegistryError

# Primary plugin vocabulary.
FactorPlugin = FactorTickPlugin
PluginSpec = FactorPluginSpec

# Backward-compatible aliases during processor -> plugin migration.
FactorProcessor = FactorPlugin
ProcessorSpec = PluginSpec
FactorRegistryError = FactorPluginRegistryError


class FactorRegistry(FactorPluginRegistry):
    def tick_plugins(self) -> tuple[FactorPlugin, ...]:
        return tuple(cast(FactorPlugin, plugin) for plugin in self.plugins())

    def processors(self) -> tuple[FactorProcessor, ...]:
        return tuple(cast(FactorProcessor, plugin) for plugin in self.tick_plugins())
