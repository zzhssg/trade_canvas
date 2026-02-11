from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from .factor_default_components import build_default_factor_components
from .factor_plugin_contract import FactorPluginSpec
from .factor_registry import FactorPlugin, FactorProcessor
from .factor_slice_plugin_contract import FactorSlicePlugin


class FactorManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorManifest:
    tick_plugins: tuple[FactorPlugin, ...]
    slice_plugins: tuple[FactorSlicePlugin, ...]

    def specs(self) -> tuple[FactorPluginSpec, ...]:
        return tuple(plugin.spec for plugin in self.tick_plugins)

    @property
    def processors(self) -> tuple[FactorProcessor, ...]:
        return tuple(cast(FactorProcessor, plugin) for plugin in self.tick_plugins)


def _specs_by_name(items: tuple[FactorPlugin, ...] | tuple[FactorSlicePlugin, ...], *, kind: str) -> dict[str, FactorPluginSpec]:
    out: dict[str, FactorPluginSpec] = {}
    for item in items:
        spec = item.spec
        name = str(spec.factor_name)
        if name in out:
            raise FactorManifestError(f"manifest_duplicate_{kind}:{name}")
        out[name] = FactorPluginSpec(factor_name=name, depends_on=tuple(spec.depends_on))
    return out


def _resolve_tick_plugins(
    *,
    tick_plugins: tuple[FactorPlugin, ...] | None,
    processors: tuple[FactorProcessor, ...] | None,
) -> tuple[FactorPlugin, ...]:
    if tick_plugins is not None and processors is not None:
        raise FactorManifestError("manifest_duplicate_tick_plugin_args")
    if tick_plugins is None and processors is None:
        raise FactorManifestError("manifest_missing_tick_plugins")
    if tick_plugins is None:
        return tuple(cast(FactorPlugin, processor) for processor in processors or ())
    return tuple(tick_plugins)


def build_factor_manifest(
    *,
    tick_plugins: tuple[FactorPlugin, ...] | None = None,
    slice_plugins: tuple[FactorSlicePlugin, ...],
    processors: tuple[FactorProcessor, ...] | None = None,
) -> FactorManifest:
    resolved_tick_plugins = _resolve_tick_plugins(tick_plugins=tick_plugins, processors=processors)
    tick_plugin_specs = _specs_by_name(resolved_tick_plugins, kind="tick_plugin")
    slice_specs = _specs_by_name(slice_plugins, kind="slice_plugin")
    if set(tick_plugin_specs.keys()) != set(slice_specs.keys()):
        only_tick_plugins = sorted(set(tick_plugin_specs.keys()) - set(slice_specs.keys()))
        only_slice = sorted(set(slice_specs.keys()) - set(tick_plugin_specs.keys()))
        raise FactorManifestError(
            f"manifest_factor_set_mismatch:only_tick_plugins={only_tick_plugins}:only_slice_plugins={only_slice}"
        )
    for name in sorted(tick_plugin_specs.keys()):
        p_spec = tick_plugin_specs[name]
        s_spec = slice_specs[name]
        if tuple(p_spec.depends_on) != tuple(s_spec.depends_on):
            raise FactorManifestError(
                f"manifest_depends_on_mismatch:{name}:tick_plugin={tuple(p_spec.depends_on)}:slice={tuple(s_spec.depends_on)}"
            )
    return FactorManifest(tick_plugins=resolved_tick_plugins, slice_plugins=slice_plugins)


def build_default_factor_manifest() -> FactorManifest:
    tick_plugins, slice_plugins = build_default_factor_components()
    return build_factor_manifest(tick_plugins=tick_plugins, slice_plugins=slice_plugins)
