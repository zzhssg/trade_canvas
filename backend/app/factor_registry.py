from __future__ import annotations

from .factor_plugin_contract import FactorTickPlugin as FactorProcessor
from .factor_plugin_contract import FactorPluginSpec as ProcessorSpec
from .factor_plugin_registry import FactorPluginRegistry, FactorPluginRegistryError

# Backward-compatible aliases during processor -> plugin migration.
FactorRegistryError = FactorPluginRegistryError


class FactorRegistry(FactorPluginRegistry):
    def processors(self) -> tuple[FactorProcessor, ...]:
        return self.plugins()
