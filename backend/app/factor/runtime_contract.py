from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, cast


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
    services: Mapping[str, Any] = field(default_factory=dict)

    def get_service(self, name: str) -> Any | None:
        key = str(name).strip()
        if not key:
            return None
        return self.services.get(key)

    def get_service_as(self, name: str, protocol_type: type[Any]) -> Any | None:
        item = self.get_service(name)
        if item is None:
            return None
        if isinstance(item, protocol_type):
            return item
        return cast(Any, item)
