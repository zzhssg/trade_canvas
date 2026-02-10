from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AnchorStrengthSelector(Protocol):
    def maybe_pick_stronger_pen(
        self,
        *,
        candidate_pen: dict[str, Any],
        kind: str,
        baseline_anchor_strength: float | None,
        current_best_ref: dict[str, int | str] | None,
        current_best_strength: float | None,
    ) -> tuple[dict[str, int | str] | None, float | None]: ...


@dataclass(frozen=True)
class FactorRuntimeContext:
    anchor_processor: AnchorStrengthSelector | None = None
