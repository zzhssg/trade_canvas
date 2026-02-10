from __future__ import annotations

from .factor_plugin_contract import FactorPlugin, FactorPluginSpec


class FactorPluginRegistryError(RuntimeError):
    pass


class FactorPluginRegistry:
    def __init__(self, plugins: list[FactorPlugin]) -> None:
        by_name: dict[str, FactorPlugin] = {}
        for p in plugins:
            name = (p.spec.factor_name or "").strip()
            if not name:
                raise FactorPluginRegistryError("empty_factor_name")
            if name in by_name:
                raise FactorPluginRegistryError(f"duplicate_factor:{name}")
            by_name[name] = p
        self._by_name = by_name

    def get(self, factor_name: str) -> FactorPlugin | None:
        return self._by_name.get(str(factor_name))

    def require(self, factor_name: str) -> FactorPlugin:
        name = str(factor_name)
        item = self._by_name.get(name)
        if item is None:
            raise FactorPluginRegistryError(f"missing_factor:{name}")
        return item

    def plugins(self) -> tuple[FactorPlugin, ...]:
        return tuple(self._by_name.values())

    def specs(self) -> tuple[FactorPluginSpec, ...]:
        return tuple(p.spec for p in self._by_name.values())
