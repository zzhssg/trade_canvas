from __future__ import annotations

from typing import Any, Iterable

from .overlay_renderer_contract import OverlayRendererPlugin


def build_overlay_event_bucket_config(
    plugins: Iterable[OverlayRendererPlugin],
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
            existing_bucket = by_kind.get(key)
            if existing_bucket is not None and existing_bucket != bucket_name:
                raise RuntimeError(f"overlay_bucket_conflict:{factor_name}:{event_kind}")
            by_kind[key] = bucket_name
            bucket_names.add(bucket_name)
            if spec.sort_keys is not None:
                sort_pair = (str(spec.sort_keys[0]), str(spec.sort_keys[1]))
                existing_sort = sort_keys.get(bucket_name)
                if existing_sort is not None and existing_sort != sort_pair:
                    raise RuntimeError(f"overlay_bucket_sort_conflict:{bucket_name}")
                sort_keys[bucket_name] = sort_pair
    return by_kind, sort_keys, tuple(sorted(bucket_names))


def collect_overlay_event_buckets(
    *,
    rows: Iterable[Any],
    event_bucket_by_kind: dict[tuple[str, str], str],
    event_bucket_sort_keys: dict[str, tuple[str, str]],
    event_bucket_names: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in event_bucket_names}
    for row in rows:
        bucket_name = event_bucket_by_kind.get((str(row.factor_name), str(row.kind)))
        if bucket_name is None:
            continue
        payload = dict(row.payload or {})
        if "candle_time" not in payload:
            payload["candle_time"] = int(row.candle_time or 0)
        if "visible_time" not in payload:
            payload["visible_time"] = int(row.candle_time or 0)
        buckets[bucket_name].append(payload)
    for bucket_name, sort_pair in event_bucket_sort_keys.items():
        key_a, key_b = sort_pair
        buckets[bucket_name].sort(key=lambda d: (int(d.get(key_a) or 0), int(d.get(key_b) or 0)))
    return buckets
