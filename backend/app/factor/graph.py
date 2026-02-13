from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorSpec:
    factor_name: str
    depends_on: tuple[str, ...] = ()


class FactorGraphError(RuntimeError):
    pass


class FactorGraph:
    """
    Deterministic DAG:
    - Validates missing deps and cycles
    - Produces a stable topological order (ties by factor_name)
    """

    def __init__(self, specs: list[FactorSpec]) -> None:
        by_name: dict[str, FactorSpec] = {}
        for s in specs:
            name = (s.factor_name or "").strip()
            if not name:
                raise FactorGraphError("empty_factor_name")
            if name in by_name:
                raise FactorGraphError(f"duplicate_factor:{name}")
            by_name[name] = FactorSpec(factor_name=name, depends_on=tuple(s.depends_on))

        missing: list[str] = []
        for s in by_name.values():
            for dep in s.depends_on:
                if dep not in by_name:
                    missing.append(f"{s.factor_name}->{dep}")
        if missing:
            missing.sort()
            raise FactorGraphError(f"missing_deps:{missing}")

        self._by_name = by_name
        self._topo = self._toposort()

    @property
    def topo_order(self) -> tuple[str, ...]:
        return self._topo

    def _toposort(self) -> tuple[str, ...]:
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []
        stack: list[str] = []

        def dfs(n: str) -> None:
            if n in visited:
                return
            if n in visiting:
                # Report cycle path for debug.
                if n in stack:
                    i = stack.index(n)
                    cycle = stack[i:] + [n]
                else:
                    cycle = stack + [n]
                raise FactorGraphError(f"cycle:{'->'.join(cycle)}")
            visiting.add(n)
            stack.append(n)
            deps = sorted(self._by_name[n].depends_on)
            for d in deps:
                dfs(d)
            stack.pop()
            visiting.remove(n)
            visited.add(n)
            order.append(n)

        for name in sorted(self._by_name.keys()):
            dfs(name)

        # order is postorder; deps appear before dependents already.
        return tuple(order)

