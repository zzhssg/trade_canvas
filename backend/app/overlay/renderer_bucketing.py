from __future__ import annotations

from typing import Any, Iterable

from ..core.event_buckets import build_event_bucket_config, collect_event_buckets
from .renderer_contract import OverlayRendererPlugin


def build_overlay_event_bucket_config(
    plugins: Iterable[OverlayRendererPlugin],
) -> tuple[dict[tuple[str, str], str], dict[str, tuple[str, str]], tuple[str, ...]]:
    return build_event_bucket_config(
        bucket_specs=(spec for plugin in plugins for spec in plugin.bucket_specs),
        conflict_prefix="overlay",
    )


def collect_overlay_event_buckets(
    *,
    rows: Iterable[Any],
    event_bucket_by_kind: dict[tuple[str, str], str],
    event_bucket_sort_keys: dict[str, tuple[str, str]],
    event_bucket_names: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    return collect_event_buckets(
        rows=rows,
        event_bucket_by_kind=event_bucket_by_kind,
        event_bucket_sort_keys=event_bucket_sort_keys,
        event_bucket_names=event_bucket_names,
    )
