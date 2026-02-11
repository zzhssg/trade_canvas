from __future__ import annotations

from .factor_graph import FactorGraph, FactorSpec
from .factor_manifest import FactorManifest, build_default_factor_manifest
from .schemas import (
    FactorCatalogItemV1,
    FactorCatalogSubFeatureV1,
    GetFactorCatalogResponseV1,
)

_EXTRA_NON_FACTOR_ITEMS: tuple[FactorCatalogItemV1, ...] = (
    FactorCatalogItemV1(
        key="sma",
        label="SMA",
        default_visible=False,
        sub_features=[
            FactorCatalogSubFeatureV1(key="sma_5", label="SMA 5", default_visible=False),
            FactorCatalogSubFeatureV1(key="sma_20", label="SMA 20", default_visible=False),
        ],
    ),
    FactorCatalogItemV1(
        key="signal",
        label="Signals",
        default_visible=False,
        sub_features=[
            FactorCatalogSubFeatureV1(key="signal.entry", label="Entry", default_visible=False),
        ],
    ),
)


def _title_from_factor_name(name: str) -> str:
    raw = str(name).replace("_", " ").replace("-", " ").strip()
    if not raw:
        return "Factor"
    return " ".join(part[:1].upper() + part[1:] for part in raw.split())


def _title_from_event_key(event_key: str) -> str:
    tail = str(event_key).split(".")[-1].strip().replace("_", " ")
    if not tail:
        return "Main"
    return " ".join(part[:1].upper() + part[1:] for part in tail.split())


def _build_factor_items_from_manifest(manifest: FactorManifest) -> list[FactorCatalogItemV1]:
    slice_plugins = {plugin.spec.factor_name: plugin for plugin in manifest.slice_plugins}
    tick_plugin_specs = {plugin.spec.factor_name: plugin.spec for plugin in manifest.tick_plugins}
    graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in manifest.specs()])

    out: list[FactorCatalogItemV1] = []
    for factor_name in graph.topo_order:
        spec = tick_plugin_specs.get(factor_name)
        catalog = spec.catalog if spec is not None else None
        label = str(catalog.label).strip() if catalog is not None and catalog.label else _title_from_factor_name(factor_name)
        default_visible = bool(catalog.default_visible) if catalog is not None else True

        if catalog is not None and catalog.sub_features:
            sub_features = [
                FactorCatalogSubFeatureV1(
                    key=str(sub.key),
                    label=str(sub.label),
                    default_visible=bool(sub.default_visible),
                )
                for sub in catalog.sub_features
            ]
        else:
            plugin = slice_plugins.get(factor_name)
            bucket_keys: list[str] = []
            if plugin is not None:
                for bucket in plugin.bucket_specs:
                    event_kind = str(bucket.event_kind)
                    if event_kind not in bucket_keys:
                        bucket_keys.append(event_kind)
            if not bucket_keys:
                bucket_keys = [factor_name]
            sub_features = [
                FactorCatalogSubFeatureV1(
                    key=key,
                    label=_title_from_event_key(key),
                    default_visible=True,
                )
                for key in bucket_keys
            ]

        out.append(
            FactorCatalogItemV1(
                key=factor_name,
                label=label,
                default_visible=default_visible,
                sub_features=sub_features,
            )
        )
    return out


def build_factor_catalog_response() -> GetFactorCatalogResponseV1:
    manifest = build_default_factor_manifest()
    factor_items = _build_factor_items_from_manifest(manifest)
    return GetFactorCatalogResponseV1(
        factors=[
            *factor_items,
            *list(_EXTRA_NON_FACTOR_ITEMS),
        ]
    )
