from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProcessorSpec:
    factor_name: str
    depends_on: tuple[str, ...] = ()


class FactorProcessor(Protocol):
    spec: ProcessorSpec


class FactorRegistryError(RuntimeError):
    pass


class FactorRegistry:
    def __init__(self, processors: list[FactorProcessor]) -> None:
        by_name: dict[str, FactorProcessor] = {}
        for p in processors:
            name = (p.spec.factor_name or "").strip()
            if not name:
                raise FactorRegistryError("empty_factor_name")
            if name in by_name:
                raise FactorRegistryError(f"duplicate_factor:{name}")
            by_name[name] = p
        self._by_name = by_name

    def get(self, factor_name: str) -> FactorProcessor | None:
        return self._by_name.get(str(factor_name))

    def require(self, factor_name: str) -> FactorProcessor:
        name = str(factor_name)
        item = self._by_name.get(name)
        if item is None:
            raise FactorRegistryError(f"missing_factor:{name}")
        return item

    def processors(self) -> tuple[FactorProcessor, ...]:
        return tuple(self._by_name.values())

    def specs(self) -> tuple[ProcessorSpec, ...]:
        return tuple(p.spec for p in self._by_name.values())
