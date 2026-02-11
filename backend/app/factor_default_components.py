from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .factor_processor_anchor import AnchorProcessor
from .factor_processor_pen import PenProcessor
from .factor_processor_pivot import PivotProcessor
from .factor_processor_zhongshu import ZhongshuProcessor
from .factor_registry import FactorPlugin
from .factor_slice_plugin_contract import FactorSlicePlugin
from .factor_slice_plugins import AnchorSlicePlugin, PenSlicePlugin, PivotSlicePlugin, ZhongshuSlicePlugin


class FactorDefaultComponentsError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorDefaultBundleSpec:
    tick_plugin_builder: Callable[[], FactorPlugin]
    slice_plugin_builder: Callable[[], FactorSlicePlugin]


def build_default_factor_bundle_specs() -> tuple[FactorDefaultBundleSpec, ...]:
    return (
        FactorDefaultBundleSpec(
            tick_plugin_builder=PivotProcessor,
            slice_plugin_builder=PivotSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            tick_plugin_builder=PenProcessor,
            slice_plugin_builder=PenSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            tick_plugin_builder=ZhongshuProcessor,
            slice_plugin_builder=ZhongshuSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            tick_plugin_builder=AnchorProcessor,
            slice_plugin_builder=AnchorSlicePlugin,
        ),
    )


def build_factor_components_from_bundles(
    *,
    bundles: tuple[FactorDefaultBundleSpec, ...],
) -> tuple[tuple[FactorPlugin, ...], tuple[FactorSlicePlugin, ...]]:
    tick_plugins: list[FactorPlugin] = []
    slice_plugins: list[FactorSlicePlugin] = []
    for bundle in bundles:
        tick_plugin = bundle.tick_plugin_builder()
        slice_plugin = bundle.slice_plugin_builder()
        tick_plugin_name = str(tick_plugin.spec.factor_name)
        slice_plugin_name = str(slice_plugin.spec.factor_name)
        if tick_plugin_name != slice_plugin_name:
            raise FactorDefaultComponentsError(
                f"factor_default_bundle_mismatch:tick_plugin={tick_plugin_name}:slice_plugin={slice_plugin_name}"
            )
        tick_plugins.append(tick_plugin)
        slice_plugins.append(slice_plugin)
    return tuple(tick_plugins), tuple(slice_plugins)


def build_default_factor_components() -> tuple[tuple[FactorPlugin, ...], tuple[FactorSlicePlugin, ...]]:
    return build_factor_components_from_bundles(bundles=build_default_factor_bundle_specs())
