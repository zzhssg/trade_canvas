from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, cast

from .graph import FactorGraph, FactorSpec
from .manifest import build_default_factor_manifest
from .plugin_registry import FactorPluginRegistry
from .slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin
from .store import FactorStore
from ..core.schemas import FactorSliceV1, GetFactorSlicesResponseV1
from ..storage.candle_store import CandleStore
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds


def _build_event_bucket_config(
    plugins: Iterable[FactorSlicePlugin],
) -> tuple[dict[tuple[str, str], str], dict[str, tuple[str, str]], tuple[str, ...]]:
    by_kind: dict[tuple[str, str], str] = {}
    sort_keys: dict[str, tuple[str, str]] = {}
    bucket_names: set[str] = set()
    for plugin in plugins:
        for spec in plugin.bucket_specs:
            factor_name = str(spec.factor_name)
            event_kind = str(spec.event_kind)
            bucket_name = str(spec.bucket_name)
            key = (factor_name, event_kind)
            old_bucket = by_kind.get(key)
            if old_bucket is not None and old_bucket != bucket_name:
                raise RuntimeError(f"factor_slice_bucket_conflict:{factor_name}:{event_kind}")
            by_kind[key] = bucket_name
            bucket_names.add(bucket_name)
            if spec.sort_keys is not None:
                sort_pair = (str(spec.sort_keys[0]), str(spec.sort_keys[1]))
                old_sort = sort_keys.get(bucket_name)
                if old_sort is not None and old_sort != sort_pair:
                    raise RuntimeError(f"factor_slice_sort_conflict:{bucket_name}")
                sort_keys[bucket_name] = sort_pair
    return by_kind, sort_keys, tuple(sorted(bucket_names))


def _is_visible_payload(payload: dict[str, Any], *, at_time: int) -> bool:
    vt = payload.get("visible_time")
    if vt is None:
        return True
    try:
        return int(vt) <= int(at_time)
    except (ValueError, TypeError):
        return True


def _collect_factor_event_buckets(
    *,
    rows: Iterable[Any],
    at_time: int,
    event_bucket_by_kind: dict[tuple[str, str], str],
    event_bucket_sort_keys: dict[str, tuple[str, str]],
    event_bucket_names: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in event_bucket_names}
    for row in rows:
        bucket = event_bucket_by_kind.get((str(row.factor_name), str(row.kind)))
        if bucket is None:
            continue
        payload = dict(row.payload or {})
        if _is_visible_payload(payload, at_time=int(at_time)):
            buckets[bucket].append(payload)

    for bucket, fields in event_bucket_sort_keys.items():
        key_a, key_b = fields
        buckets[bucket].sort(key=lambda d: (int(d.get(key_a, 0)), int(d.get(key_b, 0))))
    return buckets


def _build_default_slice_plugins_from_manifest() -> tuple[FactorSlicePlugin, ...]:
    return build_default_factor_manifest().slice_plugins


@dataclass(frozen=True)
class FactorSlicesService:
    candle_store: CandleStore
    factor_store: FactorStore
    slice_plugins: tuple[FactorSlicePlugin, ...] = field(default_factory=_build_default_slice_plugins_from_manifest)

    _topo_plugins: tuple[FactorSlicePlugin, ...] = field(init=False, repr=False)
    _event_bucket_by_kind: dict[tuple[str, str], str] = field(init=False, repr=False)
    _event_bucket_sort_keys: dict[str, tuple[str, str]] = field(init=False, repr=False)
    _event_bucket_names: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        registry = FactorPluginRegistry(list(self.slice_plugins))
        graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
        topo_plugins = tuple(cast(FactorSlicePlugin, registry.require(name)) for name in graph.topo_order)
        by_kind, sort_keys, bucket_names = _build_event_bucket_config(topo_plugins)
        object.__setattr__(self, "_topo_plugins", topo_plugins)
        object.__setattr__(self, "_event_bucket_by_kind", by_kind)
        object.__setattr__(self, "_event_bucket_sort_keys", sort_keys)
        object.__setattr__(self, "_event_bucket_names", bucket_names)

    def get_slices(self, *, series_id: str, at_time: int, window_candles: int = 2000) -> GetFactorSlicesResponseV1:
        aligned = self.candle_store.floor_time(series_id, at_time=int(at_time))
        return self.get_slices_aligned(
            series_id=series_id,
            aligned_time=aligned,
            at_time=int(at_time),
            window_candles=int(window_candles),
        )

    def get_slices_aligned(
        self,
        *,
        series_id: str,
        aligned_time: int | None,
        at_time: int,
        window_candles: int = 2000,
    ) -> GetFactorSlicesResponseV1:
        if aligned_time is None:
            return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=None)
        aligned = int(aligned_time)

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(aligned) - int(window_candles) * int(tf_s))

        factor_rows = self.factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(start_time),
            end_candle_time=int(aligned),
        )
        buckets = _collect_factor_event_buckets(
            rows=factor_rows,
            at_time=int(aligned),
            event_bucket_by_kind=self._event_bucket_by_kind,
            event_bucket_sort_keys=self._event_bucket_sort_keys,
            event_bucket_names=self._event_bucket_names,
        )

        candle_id = f"{series_id}:{int(aligned)}"
        head_rows = {
            plugin.spec.factor_name: self.factor_store.get_head_at_or_before(
                series_id=series_id,
                factor_name=plugin.spec.factor_name,
                candle_time=int(aligned),
            )
            for plugin in self._topo_plugins
        }

        snapshots: dict[str, FactorSliceV1] = {}
        factors: list[str] = []
        for plugin in self._topo_plugins:
            factor_name = plugin.spec.factor_name
            snapshot = plugin.build_snapshot(
                FactorSliceBuildContext(
                    series_id=series_id,
                    aligned_time=int(aligned),
                    at_time=int(at_time),
                    start_time=int(start_time),
                    window_candles=int(window_candles),
                    candle_id=candle_id,
                    candle_store=self.candle_store,
                    buckets=buckets,
                    head_rows=head_rows,
                    snapshots=snapshots,
                )
            )
            if snapshot is None:
                continue
            factors.append(factor_name)
            snapshots[factor_name] = snapshot

        return GetFactorSlicesResponseV1(
            series_id=series_id,
            at_time=int(aligned),
            candle_id=candle_id,
            factors=factors,
            snapshots=snapshots,
        )
