from __future__ import annotations

import unittest
from typing import Any

from backend.app.factor_default_components import (
    FactorDefaultBundleSpec,
    FactorDefaultComponentsError,
    build_default_factor_components,
    build_factor_components_from_bundles,
)
from backend.app.factor_plugin_contract import FactorPluginSpec


class _TickPlugin:
    def __init__(self, factor_name: str) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=())

    def run_tick(self, *, series_id: str, state: Any, runtime: Any) -> None:  # pragma: no cover - contract stub only
        _ = series_id
        _ = state
        _ = runtime


class _SlicePlugin:
    def __init__(self, factor_name: str) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=())
        self.bucket_specs = ()

    def build_snapshot(self, ctx):  # pragma: no cover - contract stub only
        _ = ctx
        return None


class FactorDefaultComponentsTests(unittest.TestCase):
    def test_default_components_keep_tick_plugin_and_slice_plugin_order_aligned(self) -> None:
        tick_plugins, slice_plugins = build_default_factor_components()
        self.assertEqual([plugin.spec.factor_name for plugin in tick_plugins], ["pivot", "pen", "zhongshu", "anchor"])
        self.assertEqual([p.spec.factor_name for p in slice_plugins], ["pivot", "pen", "zhongshu", "anchor"])

    def test_bundle_mismatch_raises_fail_fast_error(self) -> None:
        bundles = (
            FactorDefaultBundleSpec(
                tick_plugin_builder=lambda: _TickPlugin("pivot"),
                slice_plugin_builder=lambda: _SlicePlugin("pen"),
            ),
        )
        with self.assertRaises(FactorDefaultComponentsError) as ctx:
            _ = build_factor_components_from_bundles(bundles=bundles)
        self.assertIn("factor_default_bundle_mismatch:tick_plugin=pivot:slice_plugin=pen", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
