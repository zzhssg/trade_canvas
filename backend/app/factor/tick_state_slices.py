from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pen import PivotMajorPoint


@dataclass
class FactorTickPivotState:
    effective_pivots: list[PivotMajorPoint]
    last_major_idx: int | None
    major_candidates: list[PivotMajorPoint]


@dataclass
class FactorTickPenState:
    confirmed_pens: list[dict[str, Any]]
    new_confirmed_pen_payloads: list[dict[str, Any]]


@dataclass
class FactorTickZhongshuState:
    payload: dict[str, Any]
    formed_entries: list[dict[str, Any]]


@dataclass
class FactorTickAnchorState:
    current_ref: dict[str, Any] | None
    strength: float | None
    best_strong_pen_ref: dict[str, int | str] | None
    best_strong_pen_strength: float | None
    baseline_strength: float | None


@dataclass
class FactorTickSrState:
    major_pivots: list[dict[str, Any]]
    snapshot: dict[str, Any]
