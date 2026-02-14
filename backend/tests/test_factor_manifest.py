from __future__ import annotations

import unittest
from typing import Any

from backend.app.factor.manifest import FactorManifestError, build_default_factor_manifest, build_factor_manifest
from backend.app.factor.plugin_contract import FactorPluginSpec


class _TickPlugin:
    def __init__(self, factor_name: str, depends_on: tuple[str, ...] = ()) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=depends_on)

    def run_tick(self, *, series_id: str, state: Any, runtime: Any) -> None:  # pragma: no cover - contract stub only
        _ = series_id
        _ = state
        _ = runtime


class _SlicePlugin:
    def __init__(self, factor_name: str, depends_on: tuple[str, ...] = ()) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=depends_on)
        self.bucket_specs = ()

    def build_snapshot(self, ctx):  # pragma: no cover - not used in manifest tests
        _ = ctx
        return None


class FactorManifestTests(unittest.TestCase):
    def test_default_manifest_aligns_tick_plugins_and_slice_plugins(self) -> None:
        manifest = build_default_factor_manifest()
        tick_plugin_names = [p.spec.factor_name for p in manifest.tick_plugins]
        slice_names = [p.spec.factor_name for p in manifest.slice_plugins]
        self.assertEqual(tick_plugin_names, ["pivot", "pen", "zhongshu", "anchor", "sr"])
        self.assertEqual(slice_names, ["pivot", "pen", "zhongshu", "anchor", "sr"])

    def test_manifest_rejects_factor_set_mismatch(self) -> None:
        with self.assertRaises(FactorManifestError) as ctx:
            build_factor_manifest(
                tick_plugins=(_TickPlugin("pivot"), _TickPlugin("pen")),
                slice_plugins=(_SlicePlugin("pivot"),),
            )
        self.assertIn("manifest_factor_set_mismatch", str(ctx.exception))

    def test_manifest_rejects_depends_on_mismatch(self) -> None:
        with self.assertRaises(FactorManifestError) as ctx:
            build_factor_manifest(
                tick_plugins=(_TickPlugin("pen", depends_on=("pivot",)),),
                slice_plugins=(_SlicePlugin("pen", depends_on=()),),
            )
        self.assertIn("manifest_depends_on_mismatch:pen", str(ctx.exception))

    def test_manifest_rejects_duplicate_tick_plugin(self) -> None:
        with self.assertRaises(FactorManifestError) as ctx:
            build_factor_manifest(
                tick_plugins=(_TickPlugin("pivot"), _TickPlugin("pivot")),
                slice_plugins=(_SlicePlugin("pivot"),),
            )
        self.assertIn("manifest_duplicate_tick_plugin:pivot", str(ctx.exception))

    def test_manifest_rejects_duplicate_slice_plugin(self) -> None:
        with self.assertRaises(FactorManifestError) as ctx:
            build_factor_manifest(
                tick_plugins=(_TickPlugin("pivot"),),
                slice_plugins=(_SlicePlugin("pivot"), _SlicePlugin("pivot")),
            )
        self.assertIn("manifest_duplicate_slice_plugin:pivot", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
