from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import cast

from ..factor.graph import FactorGraph, FactorSpec
from ..factor.plugin_registry import FactorPluginRegistry
from .renderer_bucketing import build_overlay_event_bucket_config, collect_overlay_event_buckets
from .renderer_contract import (
    OverlayEventBucketSpec,
    OverlayRenderContext,
    OverlayRenderOutput,
    OverlayRendererPlugin,
)
from .renderer_marker import MarkerOverlayRenderer
from .renderer_pen import PenOverlayRenderer
from .renderer_sr import SrOverlayRenderer
from .renderer_structure import StructureOverlayRenderer

_BUILD_RENDERER_ATTR = "build_renderer"
_RENDERER_MODULE_PREFIX = "renderer_"
_RENDERER_SKIP_MODULES = frozenset(
    {
        "renderer_bucketing",
        "renderer_contract",
        "renderer_plugins",
        "renderer_structure_helpers",
    }
)


class OverlayRendererDiscoveryError(RuntimeError):
    pass


def _iter_renderer_module_names() -> tuple[str, ...]:
    names: list[str] = []
    package_dir = Path(__file__).resolve().parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        module_name = str(module_info.name)
        if not module_name.startswith(_RENDERER_MODULE_PREFIX):
            continue
        if module_name in _RENDERER_SKIP_MODULES:
            continue
        names.append(module_name)
    if not names:
        raise OverlayRendererDiscoveryError("overlay_renderer_discovery_empty")
    names.sort()
    return tuple(names)


def _import_renderer_module(module_name: str) -> ModuleType:
    qualified_name = f"{__package__}.{module_name}"
    try:
        return importlib.import_module(qualified_name)
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise OverlayRendererDiscoveryError(f"overlay_renderer_import_failed:{qualified_name}:{exc}") from exc


def _build_plugin_from_module(module_name: str) -> OverlayRendererPlugin:
    module = _import_renderer_module(module_name)
    factory = getattr(module, _BUILD_RENDERER_ATTR, None)
    if not callable(factory):
        raise OverlayRendererDiscoveryError(f"overlay_renderer_missing_factory:{module.__name__}")
    try:
        plugin = factory()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise OverlayRendererDiscoveryError(f"overlay_renderer_factory_failed:{module.__name__}:{exc}") from exc
    return cast(OverlayRendererPlugin, plugin)


def build_default_overlay_render_plugins() -> tuple[OverlayRendererPlugin, ...]:
    plugins_by_name: dict[str, OverlayRendererPlugin] = {}
    specs: list[FactorSpec] = []

    for module_name in _iter_renderer_module_names():
        plugin = _build_plugin_from_module(module_name)
        plugin_name = str(plugin.spec.factor_name or "").strip()
        if not plugin_name:
            raise OverlayRendererDiscoveryError(f"overlay_renderer_empty_name:{module_name}")
        if plugin_name in plugins_by_name:
            raise OverlayRendererDiscoveryError(f"overlay_renderer_duplicate:{plugin_name}")

        depends_on = tuple(plugin.spec.depends_on)
        plugins_by_name[plugin_name] = plugin
        specs.append(FactorSpec(factor_name=plugin_name, depends_on=depends_on))

    registry = FactorPluginRegistry(list(plugins_by_name.values()))
    try:
        graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
    except Exception as exc:
        raise OverlayRendererDiscoveryError(f"overlay_renderer_graph_invalid:{exc}") from exc
    return tuple(cast(OverlayRendererPlugin, registry.require(name)) for name in graph.topo_order)


__all__ = [
    "MarkerOverlayRenderer",
    "OverlayEventBucketSpec",
    "OverlayRenderContext",
    "OverlayRenderOutput",
    "OverlayRendererPlugin",
    "PenOverlayRenderer",
    "SrOverlayRenderer",
    "StructureOverlayRenderer",
    "OverlayRendererDiscoveryError",
    "build_default_overlay_render_plugins",
    "build_overlay_event_bucket_config",
    "collect_overlay_event_buckets",
]
