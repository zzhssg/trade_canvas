from __future__ import annotations

import pytest

from backend.app.factor.capability_manifest import (
    FactorCapabilityManifestError,
    FactorCapabilitySpec,
    build_default_factor_capability_manifest,
    build_factor_capability_manifest,
    capability_map,
)
from backend.app.factor.manifest import build_default_factor_manifest


def test_default_capability_manifest_follows_factor_manifest_order() -> None:
    manifest = build_default_factor_manifest()
    capabilities = build_default_factor_capability_manifest(manifest=manifest)

    expected_order = [spec.factor_name for spec in manifest.specs()]
    actual_order = [item.factor_name for item in capabilities]
    assert actual_order == expected_order
    assert all(item.enable_replay_package for item in capabilities)
    assert all(not item.enable_overlay for item in capabilities)
    assert all(not item.enable_feature for item in capabilities)
    assert all(not item.enable_freqtrade_live for item in capabilities)
    assert all(not item.enable_backtest_package for item in capabilities)


def test_capability_manifest_accepts_known_override() -> None:
    manifest = build_default_factor_manifest()
    override = FactorCapabilitySpec(
        factor_name="pen",
        enable_overlay=True,
        enable_feature=True,
        enable_freqtrade_live=True,
        enable_backtest_package=True,
        enable_replay_package=True,
    )
    capabilities = build_default_factor_capability_manifest(
        manifest=manifest,
        overrides={"pen": override},
    )
    by_name = capability_map(capabilities)
    assert by_name["pen"].enable_overlay is True
    assert by_name["pen"].enable_feature is True
    assert by_name["pen"].enable_freqtrade_live is True
    assert by_name["pen"].enable_backtest_package is True
    assert by_name["pen"].enable_replay_package is True
    assert by_name["pivot"].enable_overlay is False


def test_capability_manifest_rejects_unknown_override() -> None:
    manifest = build_default_factor_manifest()
    with pytest.raises(FactorCapabilityManifestError, match="capability_override_unknown_factor"):
        build_default_factor_capability_manifest(
            manifest=manifest,
            overrides={"unknown": FactorCapabilitySpec(factor_name="unknown", enable_overlay=True)},
        )


def test_capability_manifest_rejects_duplicate_factor_name() -> None:
    with pytest.raises(FactorCapabilityManifestError, match="capability_duplicate_factor:pen"):
        build_factor_capability_manifest(
            factor_names=("pen", "pen"),
            overrides=None,
        )

