from __future__ import annotations

from .factor_processor_anchor import AnchorProcessor
from .factor_processor_pen import PenProcessor
from .factor_processor_pivot import PivotProcessor
from .factor_processor_slice_buckets import SliceBucketSpec, build_default_slice_bucket_specs
from .factor_processor_zhongshu import ZhongshuProcessor
from .factor_registry import FactorProcessor


def build_default_factor_processors() -> list[FactorProcessor]:
    return [PivotProcessor(), PenProcessor(), ZhongshuProcessor(), AnchorProcessor()]


__all__ = [
    "AnchorProcessor",
    "PenProcessor",
    "PivotProcessor",
    "SliceBucketSpec",
    "ZhongshuProcessor",
    "build_default_factor_processors",
    "build_default_slice_bucket_specs",
]
