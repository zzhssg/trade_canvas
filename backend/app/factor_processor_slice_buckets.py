from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SliceBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


def build_default_slice_bucket_specs() -> tuple[SliceBucketSpec, ...]:
    return (
        SliceBucketSpec(
            factor_name="pivot",
            event_kind="pivot.major",
            bucket_name="piv_major",
            sort_keys=("visible_time", "pivot_time"),
        ),
        SliceBucketSpec(
            factor_name="pivot",
            event_kind="pivot.minor",
            bucket_name="piv_minor",
        ),
        SliceBucketSpec(
            factor_name="pen",
            event_kind="pen.confirmed",
            bucket_name="pen_confirmed",
            sort_keys=("visible_time", "start_time"),
        ),
        SliceBucketSpec(
            factor_name="zhongshu",
            event_kind="zhongshu.dead",
            bucket_name="zhongshu_dead",
        ),
        SliceBucketSpec(
            factor_name="anchor",
            event_kind="anchor.switch",
            bucket_name="anchor_switches",
            sort_keys=("visible_time", "switch_time"),
        ),
    )
