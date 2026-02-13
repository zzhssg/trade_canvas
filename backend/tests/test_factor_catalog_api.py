from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.factor.catalog import build_factor_catalog_response
from backend.app.factor.manifest import build_factor_manifest
from backend.app.factor.plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec, FactorPluginSpec
from backend.app.main import create_app


class _TickPlugin:
    def __init__(self) -> None:
        self.spec = FactorPluginSpec(
            factor_name="custom_factor",
            depends_on=(),
            catalog=FactorCatalogSpec(
                label="Custom Factor",
                default_visible=False,
                sub_features=(
                    FactorCatalogSubFeatureSpec(
                        key="custom.signal",
                        label="Custom Signal",
                        default_visible=False,
                    ),
                ),
            ),
        )

    def run_tick(self, *, series_id, state, runtime) -> None:
        _ = series_id
        _ = state
        _ = runtime


class _SlicePlugin:
    def __init__(self) -> None:
        self.spec = FactorPluginSpec(factor_name="custom_factor", depends_on=())
        self.bucket_specs = ()

    def build_snapshot(self, ctx):  # pragma: no cover - not needed in this test
        _ = ctx
        return None


class FactorCatalogApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_factor_catalog_contains_default_factor_and_virtual_groups(self) -> None:
        res = self.client.get("/api/factor/catalog")
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(int(payload.get("schema_version") or 0), 1)

        factors = payload.get("factors") or []
        keys = [str(item.get("key") or "") for item in factors]
        self.assertEqual(keys[:4], ["pivot", "pen", "zhongshu", "anchor"])
        self.assertIn("sma", keys)
        self.assertIn("signal", keys)

        by_key = {str(item.get("key") or ""): item for item in factors}
        self.assertEqual(
            [str(item.get("key") or "") for item in by_key["pivot"].get("sub_features") or []],
            ["pivot.major", "pivot.minor"],
        )
        self.assertEqual(
            [str(item.get("key") or "") for item in by_key["pen"].get("sub_features") or []],
            ["pen.confirmed", "pen.extending", "pen.candidate"],
        )
        self.assertFalse(bool(by_key["sma"].get("default_visible")))
        self.assertFalse(bool(by_key["signal"].get("default_visible")))

    def test_factor_catalog_uses_tick_plugin_catalog_metadata(self) -> None:
        manifest = build_factor_manifest(
            tick_plugins=(_TickPlugin(),),
            slice_plugins=(_SlicePlugin(),),
        )
        with patch("backend.app.factor.catalog.build_default_factor_manifest", return_value=manifest):
            payload = build_factor_catalog_response().model_dump()

        factors = payload.get("factors") or []
        self.assertGreaterEqual(len(factors), 1)
        custom = factors[0]
        self.assertEqual(custom.get("key"), "custom_factor")
        self.assertEqual(custom.get("label"), "Custom Factor")
        self.assertFalse(bool(custom.get("default_visible")))
        self.assertEqual(
            custom.get("sub_features"),
            [
                {
                    "key": "custom.signal",
                    "label": "Custom Signal",
                    "default_visible": False,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
