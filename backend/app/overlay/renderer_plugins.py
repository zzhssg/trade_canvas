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

_FACTORY_ATTR = "build_renderer_plugin"
_MODULE_PREFIX = "renderer_"
_EXCLUDED_MODULES = {
    "renderer_plugins",
    "renderer_contract",
    "renderer_bucketing",
    "renderer_structure_helpers",
}


class OverlayRendererDiscoveryError(RuntimeError):
    pass


def _renderer_module_names() -> tuple[str, ...]:
    package_dir = Path(__file__).resolve().parent
    names: list[str] = []
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        module_name = str(module_info.name)
        if not module_name.startswith(_MODULE_PREFIX):
            continue
        if module_name in _EXCLUDED_MODULES:
            continue
        names.append(module_name)
    if not names:
        raise OverlayRendererDiscoveryError("overlay_renderer_discovery_empty")
    names.sort()
    return tuple(names)


def _import_renderer_module(module_name: str) -> ModuleType:
    package_name = __name__.rsplit(".", 1)[0]
    qualified_name = f"{package_name}.{module_name}"
    try:
        return importlib.import_module(qualified_name)
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise OverlayRendererDiscoveryError(f"overlay_renderer_import_failed:{qualified_name}:{exc}") from exc


def _build_renderer(module_name: str) -> OverlayRendererPlugin:
    module = _import_renderer_module(module_name)
    factory = getattr(module, _FACTORY_ATTR, None)
    if not callable(factory):
        raise OverlayRendererDiscoveryError(f"overlay_renderer_missing_factory:{module.__name__}")
    try:
        plugin = factory()
    except Exception as exc:  # pragma: no cover - fail-fast branch
        raise OverlayRendererDiscoveryError(f"overlay_renderer_factory_failed:{module.__name__}:{exc}") from exc
    spec = getattr(plugin, "spec", None)
    factor_name = str(getattr(spec, "factor_name", "") or "").strip()
    if not factor_name:
        raise OverlayRendererDiscoveryError(f"overlay_renderer_empty_name:{module.__name__}")
    bucket_specs = getattr(plugin, "bucket_specs", None)
    render = getattr(plugin, "render", None)
    if not isinstance(bucket_specs, tuple) or not callable(render):
        raise OverlayRendererDiscoveryError(f"overlay_renderer_invalid_plugin:{module.__name__}")
    return cast(OverlayRendererPlugin, plugin)


def build_default_overlay_render_plugins() -> tuple[OverlayRendererPlugin, ...]:
    plugins_by_name: dict[str, OverlayRendererPlugin] = {}
    for module_name in _renderer_module_names():
        plugin = _build_renderer(module_name)
        factor_name = str(plugin.spec.factor_name)
        if factor_name in plugins_by_name:
            raise OverlayRendererDiscoveryError(f"overlay_renderer_duplicate:{factor_name}")
        plugins_by_name[factor_name] = plugin

    registry = FactorPluginRegistry(list(plugins_by_name.values()))
    graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
    return tuple(cast(OverlayRendererPlugin, registry.require(name)) for name in graph.topo_order)


__all__ = [
    "MarkerOverlayRenderer",
    "OverlayEventBucketSpec",
    "OverlayRenderContext",
    "OverlayRenderOutput",
    "OverlayRendererPlugin",
    "OverlayRendererDiscoveryError",
    "PenOverlayRenderer",
    "SrOverlayRenderer",
    "StructureOverlayRenderer",
    "build_default_overlay_render_plugins",
    "build_overlay_event_bucket_config",
    "collect_overlay_event_buckets",
]
