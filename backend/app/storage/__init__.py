from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "CandleRepository",
    "FactorRepository",
    "OverlayRepository",
    "PostgresPool",
    "PostgresPoolSettings",
    "PostgresFactorRepository",
    "PostgresOverlayRepository",
    "PostgresCandleRepository",
    "build_postgres_bootstrap_sql",
    "bootstrap_postgres_schema",
    "CandleStore",
    "LocalConnectionBase",
    "MemoryCursor",
    "MemoryRow",
]

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "CandleRepository": (".contracts", "CandleRepository"),
    "FactorRepository": (".contracts", "FactorRepository"),
    "OverlayRepository": (".contracts", "OverlayRepository"),
    "PostgresPool": (".postgres_pool", "PostgresPool"),
    "PostgresPoolSettings": (".postgres_pool", "PostgresPoolSettings"),
    "PostgresFactorRepository": (".postgres_factor_repo", "PostgresFactorRepository"),
    "PostgresOverlayRepository": (".postgres_overlay_repo", "PostgresOverlayRepository"),
    "PostgresCandleRepository": (".postgres_repos", "PostgresCandleRepository"),
    "build_postgres_bootstrap_sql": (".postgres_schema", "build_postgres_bootstrap_sql"),
    "bootstrap_postgres_schema": (".postgres_schema", "bootstrap_postgres_schema"),
    "CandleStore": (".candle_store", "CandleStore"),
    "LocalConnectionBase": (".local_store_runtime", "LocalConnectionBase"),
    "MemoryCursor": (".local_store_runtime", "MemoryCursor"),
    "MemoryRow": (".local_store_runtime", "MemoryRow"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
