from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SliceBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


def build_default_slice_bucket_specs() -> tuple[SliceBucketSpec, ...]:
    from .factor_slice_plugins import build_default_factor_slice_plugins

    specs: list[SliceBucketSpec] = []
    for plugin in build_default_factor_slice_plugins():
        specs.extend(plugin.bucket_specs)
    return tuple(specs)
