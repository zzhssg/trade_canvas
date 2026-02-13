from __future__ import annotations

"""默认 factor slice 插件导出层。"""

from .bundles.anchor import AnchorSlicePlugin
from .bundles.pen import PenSlicePlugin
from .bundles.pivot import PivotSlicePlugin
from .bundles.zhongshu import ZhongshuSlicePlugin
from .default_components import build_default_factor_components
from .slice_plugin_contract import FactorSlicePlugin


def build_default_factor_slice_plugins() -> tuple[FactorSlicePlugin, ...]:
    _, slice_plugins = build_default_factor_components()
    return slice_plugins


__all__ = [
    "AnchorSlicePlugin",
    "PenSlicePlugin",
    "PivotSlicePlugin",
    "ZhongshuSlicePlugin",
    "build_default_factor_slice_plugins",
]
