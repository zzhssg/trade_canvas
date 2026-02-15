from __future__ import annotations

from typing import Any

from .signal_plugin_contract import FreqtradeSignalBucketSpec


def feature_kind_key(*, factor_name: str, event_kind: str) -> str:
    factor = str(factor_name or "").strip()
    kind = str(event_kind or "").strip()
    prefix = f"{factor}."
    if factor and kind.startswith(prefix):
        kind = kind[len(prefix) :]
    normalized = kind.replace(".", "_").strip("_")
    return normalized or "event"


def required_feature_factors(*, bucket_specs: tuple[FreqtradeSignalBucketSpec, ...]) -> tuple[str, ...]:
    names = {str(spec.factor_name).strip() for spec in bucket_specs if str(spec.factor_name).strip()}
    return tuple(sorted(names))


def to_positive_int(value: Any) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def build_signal_buckets_from_features(
    *,
    bucket_specs: tuple[FreqtradeSignalBucketSpec, ...],
    feature_rows_by_time: dict[int, dict[str, Any]],
    times: list[int],
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    ordered_times = sorted({int(t) for t in times if int(t) > 0})
    for spec in bucket_specs:
        factor_name = str(spec.factor_name)
        kind_key = feature_kind_key(
            factor_name=factor_name,
            event_kind=str(spec.event_kind),
        )
        count_key = f"{factor_name}_{kind_key}_count"
        direction_key = f"{factor_name}_{kind_key}_direction"
        bucket: list[dict[str, Any]] = []
        for candle_time in ordered_times:
            values = feature_rows_by_time.get(int(candle_time)) or {}
            count = to_positive_int(values.get(count_key))
            if count <= 0:
                continue
            direction = values.get(direction_key)
            payload: dict[str, Any] = {
                "candle_time": int(candle_time),
                "visible_time": int(candle_time),
                "count": int(count),
            }
            for sort_key in tuple(spec.sort_keys or ()):
                payload[str(sort_key)] = int(candle_time)
            if direction is not None:
                payload["direction"] = direction
            bucket.append(payload)
        out[str(spec.bucket_name)] = bucket
    return out
