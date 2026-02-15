from __future__ import annotations

import pytest

from backend.app.feature.contracts import (
    FeatureColumnSpec,
    FeatureContractError,
    normalize_feature_row_values,
    validate_feature_columns,
)


def test_validate_feature_columns_normalizes_and_keeps_order() -> None:
    columns = validate_feature_columns(
        (
            FeatureColumnSpec(key="trend_score", source_factor="trend", value_type="float", nullable=False),
            FeatureColumnSpec(key="trend_flag", source_factor="trend", value_type="bool", nullable=True),
        )
    )
    assert [c.key for c in columns] == ["trend_score", "trend_flag"]
    assert columns[0].nullable is False
    assert columns[1].nullable is True


def test_validate_feature_columns_rejects_duplicate_key() -> None:
    with pytest.raises(FeatureContractError, match="feature_key_duplicate:score"):
        validate_feature_columns(
            (
                FeatureColumnSpec(key="score", source_factor="trend"),
                FeatureColumnSpec(key="score", source_factor="trend"),
            )
        )


def test_normalize_feature_row_values_rejects_unknown_key() -> None:
    columns = (
        FeatureColumnSpec(key="trend_score", source_factor="trend", nullable=False),
    )
    with pytest.raises(FeatureContractError, match="feature_value_unknown_key:other"):
        normalize_feature_row_values(columns=columns, values={"other": 1.2})


def test_normalize_feature_row_values_requires_non_nullable_columns() -> None:
    columns = (
        FeatureColumnSpec(key="trend_score", source_factor="trend", nullable=False),
        FeatureColumnSpec(key="trend_flag", source_factor="trend", nullable=True),
    )
    with pytest.raises(FeatureContractError, match="feature_value_missing_non_nullable:trend_score"):
        normalize_feature_row_values(columns=columns, values={"trend_flag": True})


def test_normalize_feature_row_values_fills_nullable_columns_with_none() -> None:
    columns = (
        FeatureColumnSpec(key="trend_score", source_factor="trend", nullable=False),
        FeatureColumnSpec(key="trend_flag", source_factor="trend", nullable=True),
    )
    values = normalize_feature_row_values(columns=columns, values={"trend_score": 1.5})
    assert values["trend_score"] == 1.5
    assert values["trend_flag"] is None

