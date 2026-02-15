from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

_FEATURE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class FeatureContractError(RuntimeError):
    pass


FeatureValue = float | int | bool | str | None


@dataclass(frozen=True)
class FeatureColumnSpec:
    key: str
    source_factor: str
    value_type: str = "float"
    nullable: bool = True


@dataclass(frozen=True)
class FeatureVectorRowV1:
    series_id: str
    candle_time: int
    candle_id: str
    values: Mapping[str, FeatureValue]


@dataclass(frozen=True)
class FeatureVectorBatchV1:
    series_id: str
    aligned_time: int
    columns: tuple[FeatureColumnSpec, ...]
    rows: tuple[FeatureVectorRowV1, ...]


def _normalize_feature_key(raw: str) -> str:
    key = str(raw or "").strip()
    if not key:
        raise FeatureContractError("feature_key_empty")
    if not _FEATURE_NAME_RE.fullmatch(key):
        raise FeatureContractError(f"feature_key_invalid:{key}")
    return key


def _normalize_factor_name(raw: str) -> str:
    name = str(raw or "").strip()
    if not name:
        raise FeatureContractError("feature_source_factor_empty")
    return name


def validate_feature_columns(
    columns: tuple[FeatureColumnSpec, ...],
) -> tuple[FeatureColumnSpec, ...]:
    out: list[FeatureColumnSpec] = []
    seen_keys: set[str] = set()
    for column in columns:
        key = _normalize_feature_key(column.key)
        if key in seen_keys:
            raise FeatureContractError(f"feature_key_duplicate:{key}")
        seen_keys.add(key)
        source_factor = _normalize_factor_name(column.source_factor)
        out.append(
            FeatureColumnSpec(
                key=key,
                source_factor=source_factor,
                value_type=str(column.value_type or "float"),
                nullable=bool(column.nullable),
            )
        )
    return tuple(out)


def normalize_feature_row_values(
    *,
    columns: tuple[FeatureColumnSpec, ...],
    values: Mapping[str, FeatureValue],
) -> dict[str, FeatureValue]:
    normalized_columns = validate_feature_columns(columns)
    column_by_key = {c.key: c for c in normalized_columns}
    out: dict[str, FeatureValue] = {}
    for key, value in (values or {}).items():
        name = _normalize_feature_key(key)
        spec = column_by_key.get(name)
        if spec is None:
            raise FeatureContractError(f"feature_value_unknown_key:{name}")
        if value is None and not spec.nullable:
            raise FeatureContractError(f"feature_value_non_nullable:{name}")
        out[name] = value

    for column in normalized_columns:
        if column.key in out:
            continue
        if column.nullable:
            out[column.key] = None
            continue
        raise FeatureContractError(f"feature_value_missing_non_nullable:{column.key}")
    return out

