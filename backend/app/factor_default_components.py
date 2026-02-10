from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .factor_processor_anchor import AnchorProcessor
from .factor_processor_pen import PenProcessor
from .factor_processor_pivot import PivotProcessor
from .factor_processor_zhongshu import ZhongshuProcessor
from .factor_registry import FactorProcessor
from .factor_slice_plugin_contract import FactorSlicePlugin
from .factor_slice_plugins import AnchorSlicePlugin, PenSlicePlugin, PivotSlicePlugin, ZhongshuSlicePlugin


class FactorDefaultComponentsError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorDefaultBundleSpec:
    processor_builder: Callable[[], FactorProcessor]
    slice_plugin_builder: Callable[[], FactorSlicePlugin]


def build_default_factor_bundle_specs() -> tuple[FactorDefaultBundleSpec, ...]:
    return (
        FactorDefaultBundleSpec(
            processor_builder=PivotProcessor,
            slice_plugin_builder=PivotSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            processor_builder=PenProcessor,
            slice_plugin_builder=PenSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            processor_builder=ZhongshuProcessor,
            slice_plugin_builder=ZhongshuSlicePlugin,
        ),
        FactorDefaultBundleSpec(
            processor_builder=AnchorProcessor,
            slice_plugin_builder=AnchorSlicePlugin,
        ),
    )


def build_factor_components_from_bundles(
    *,
    bundles: tuple[FactorDefaultBundleSpec, ...],
) -> tuple[tuple[FactorProcessor, ...], tuple[FactorSlicePlugin, ...]]:
    processors: list[FactorProcessor] = []
    slice_plugins: list[FactorSlicePlugin] = []
    for bundle in bundles:
        processor = bundle.processor_builder()
        slice_plugin = bundle.slice_plugin_builder()
        processor_name = str(processor.spec.factor_name)
        slice_plugin_name = str(slice_plugin.spec.factor_name)
        if processor_name != slice_plugin_name:
            raise FactorDefaultComponentsError(
                f"factor_default_bundle_mismatch:processor={processor_name}:slice_plugin={slice_plugin_name}"
            )
        processors.append(processor)
        slice_plugins.append(slice_plugin)
    return tuple(processors), tuple(slice_plugins)


def build_default_factor_components() -> tuple[tuple[FactorProcessor, ...], tuple[FactorSlicePlugin, ...]]:
    return build_factor_components_from_bundles(bundles=build_default_factor_bundle_specs())
