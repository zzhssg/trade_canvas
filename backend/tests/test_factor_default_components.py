from __future__ import annotations

import unittest

from backend.app.factor_default_components import (
    FactorDefaultBundleSpec,
    FactorDefaultComponentsError,
    build_default_factor_components,
    build_factor_components_from_bundles,
)
from backend.app.factor_plugin_contract import FactorPluginSpec


class _Processor:
    def __init__(self, factor_name: str) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=())


class _SlicePlugin:
    def __init__(self, factor_name: str) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=())
        self.bucket_specs = ()

    def build_snapshot(self, ctx):  # pragma: no cover - contract stub only
        _ = ctx
        return None


class FactorDefaultComponentsTests(unittest.TestCase):
    def test_default_components_keep_processor_and_slice_plugin_order_aligned(self) -> None:
        processors, slice_plugins = build_default_factor_components()
        self.assertEqual([p.spec.factor_name for p in processors], ["pivot", "pen", "zhongshu", "anchor"])
        self.assertEqual([p.spec.factor_name for p in slice_plugins], ["pivot", "pen", "zhongshu", "anchor"])

    def test_bundle_mismatch_raises_fail_fast_error(self) -> None:
        bundles = (
            FactorDefaultBundleSpec(
                processor_builder=lambda: _Processor("pivot"),
                slice_plugin_builder=lambda: _SlicePlugin("pen"),
            ),
        )
        with self.assertRaises(FactorDefaultComponentsError) as ctx:
            _ = build_factor_components_from_bundles(bundles=bundles)
        self.assertIn("factor_default_bundle_mismatch:processor=pivot:slice_plugin=pen", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
