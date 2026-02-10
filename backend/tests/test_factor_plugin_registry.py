from __future__ import annotations

import unittest

from backend.app.factor_plugin_contract import FactorPluginSpec
from backend.app.factor_plugin_registry import FactorPluginRegistry, FactorPluginRegistryError


class _Plugin:
    def __init__(self, factor_name: str, depends_on: tuple[str, ...] = ()) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=depends_on)


class FactorPluginRegistryTests(unittest.TestCase):
    def test_registry_rejects_duplicate_factor_name(self) -> None:
        with self.assertRaises(FactorPluginRegistryError) as ctx:
            FactorPluginRegistry([_Plugin("pivot"), _Plugin("pivot")])
        self.assertIn("duplicate_factor:pivot", str(ctx.exception))

    def test_registry_rejects_empty_name(self) -> None:
        with self.assertRaises(FactorPluginRegistryError) as ctx:
            FactorPluginRegistry([_Plugin("")])
        self.assertIn("empty_factor_name", str(ctx.exception))

    def test_specs_and_require(self) -> None:
        reg = FactorPluginRegistry([_Plugin("pivot"), _Plugin("pen", depends_on=("pivot",))])
        self.assertEqual([s.factor_name for s in reg.specs()], ["pivot", "pen"])
        self.assertEqual(reg.require("pen").spec.depends_on, ("pivot",))
        with self.assertRaises(FactorPluginRegistryError):
            reg.require("missing")


if __name__ == "__main__":
    unittest.main()
