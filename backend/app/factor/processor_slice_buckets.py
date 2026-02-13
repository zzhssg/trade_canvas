from __future__ import annotations

from .default_components import build_default_factor_components
from .slice_plugin_contract import SliceBucketSpec


def build_default_slice_bucket_specs() -> tuple[SliceBucketSpec, ...]:
    specs: list[SliceBucketSpec] = []
    _, slice_plugins = build_default_factor_components()
    for plugin in slice_plugins:
        specs.extend(plugin.bucket_specs)
    return tuple(specs)
