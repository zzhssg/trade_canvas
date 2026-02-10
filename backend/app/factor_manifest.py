from __future__ import annotations

from dataclasses import dataclass

from .factor_default_components import build_default_factor_components
from .factor_plugin_contract import FactorPluginSpec
from .factor_registry import FactorProcessor
from .factor_slice_plugin_contract import FactorSlicePlugin


class FactorManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorManifest:
    processors: tuple[FactorProcessor, ...]
    slice_plugins: tuple[FactorSlicePlugin, ...]

    def specs(self) -> tuple[FactorPluginSpec, ...]:
        return tuple(p.spec for p in self.processors)


def _specs_by_name(items: tuple[FactorProcessor, ...] | tuple[FactorSlicePlugin, ...], *, kind: str) -> dict[str, FactorPluginSpec]:
    out: dict[str, FactorPluginSpec] = {}
    for item in items:
        spec = item.spec
        name = str(spec.factor_name)
        if name in out:
            raise FactorManifestError(f"manifest_duplicate_{kind}:{name}")
        out[name] = FactorPluginSpec(factor_name=name, depends_on=tuple(spec.depends_on))
    return out


def build_factor_manifest(
    *,
    processors: tuple[FactorProcessor, ...],
    slice_plugins: tuple[FactorSlicePlugin, ...],
) -> FactorManifest:
    processor_specs = _specs_by_name(processors, kind="processor")
    slice_specs = _specs_by_name(slice_plugins, kind="slice_plugin")
    if set(processor_specs.keys()) != set(slice_specs.keys()):
        only_processors = sorted(set(processor_specs.keys()) - set(slice_specs.keys()))
        only_slice = sorted(set(slice_specs.keys()) - set(processor_specs.keys()))
        raise FactorManifestError(
            f"manifest_factor_set_mismatch:only_processors={only_processors}:only_slice_plugins={only_slice}"
        )
    for name in sorted(processor_specs.keys()):
        p_spec = processor_specs[name]
        s_spec = slice_specs[name]
        if tuple(p_spec.depends_on) != tuple(s_spec.depends_on):
            raise FactorManifestError(
                f"manifest_depends_on_mismatch:{name}:processor={tuple(p_spec.depends_on)}:slice={tuple(s_spec.depends_on)}"
            )
    return FactorManifest(processors=processors, slice_plugins=slice_plugins)


def build_default_factor_manifest() -> FactorManifest:
    processors, slice_plugins = build_default_factor_components()
    return build_factor_manifest(processors=processors, slice_plugins=slice_plugins)
