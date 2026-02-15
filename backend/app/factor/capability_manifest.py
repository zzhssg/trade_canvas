from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .manifest import FactorManifest, build_default_factor_manifest


class FactorCapabilityManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorCapabilitySpec:
    factor_name: str
    enable_overlay: bool = True
    enable_feature: bool = True
    enable_freqtrade_live: bool = True
    enable_backtest_package: bool = True
    enable_replay_package: bool = True


def _normalize_factor_name(value: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise FactorCapabilityManifestError("capability_empty_factor_name")
    return name


def _dedupe_factor_names(factor_names: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in factor_names:
        name = _normalize_factor_name(raw)
        if name in seen:
            raise FactorCapabilityManifestError(f"capability_duplicate_factor:{name}")
        seen.add(name)
        out.append(name)
    return tuple(out)


def _normalize_override_map(
    overrides: Mapping[str, FactorCapabilitySpec] | None,
) -> dict[str, FactorCapabilitySpec]:
    out: dict[str, FactorCapabilitySpec] = {}
    for key, override in (overrides or {}).items():
        override_key = _normalize_factor_name(str(key))
        if not isinstance(override, FactorCapabilitySpec):
            raise FactorCapabilityManifestError(f"capability_override_invalid:{override_key}")
        override_name = _normalize_factor_name(override.factor_name)
        if override_name != override_key:
            raise FactorCapabilityManifestError(
                f"capability_override_name_mismatch:{override_key}:{override_name}"
            )
        out[override_key] = override
    return out


def build_factor_capability_manifest(
    *,
    factor_names: tuple[str, ...],
    overrides: Mapping[str, FactorCapabilitySpec] | None = None,
) -> tuple[FactorCapabilitySpec, ...]:
    ordered_names = _dedupe_factor_names(factor_names)
    override_map = _normalize_override_map(overrides)
    unknown_override_names = sorted(set(override_map.keys()) - set(ordered_names))
    if unknown_override_names:
        raise FactorCapabilityManifestError(
            f"capability_override_unknown_factor:{unknown_override_names}"
        )

    out: list[FactorCapabilitySpec] = []
    for name in ordered_names:
        base = FactorCapabilitySpec(factor_name=name)
        override = override_map.get(name)
        if override is None:
            out.append(base)
            continue
        out.append(replace(override, factor_name=name))
    return tuple(out)


def build_default_factor_capability_manifest(
    *,
    manifest: FactorManifest | None = None,
    overrides: Mapping[str, FactorCapabilitySpec] | None = None,
) -> tuple[FactorCapabilitySpec, ...]:
    factor_manifest = manifest or build_default_factor_manifest()
    factor_names = tuple(str(spec.factor_name) for spec in factor_manifest.specs())
    return build_factor_capability_manifest(
        factor_names=factor_names,
        overrides=overrides,
    )


def capability_map(
    capabilities: tuple[FactorCapabilitySpec, ...],
) -> dict[str, FactorCapabilitySpec]:
    out: dict[str, FactorCapabilitySpec] = {}
    for item in capabilities:
        name = _normalize_factor_name(item.factor_name)
        if name in out:
            raise FactorCapabilityManifestError(f"capability_duplicate_factor:{name}")
        out[name] = item
    return out
