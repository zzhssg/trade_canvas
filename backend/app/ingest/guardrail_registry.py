from __future__ import annotations

from .loop_guardrail import IngestLoopGuardrail, IngestLoopGuardrailConfig


class IngestGuardrailRegistry:
    def __init__(
        self,
        *,
        enabled: bool,
        config: IngestLoopGuardrailConfig | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._config = config or IngestLoopGuardrailConfig()
        self._guardrails: dict[str, IngestLoopGuardrail] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._enabled)

    def get(self, series_id: str) -> IngestLoopGuardrail | None:
        if not self._enabled:
            return None
        guardrail = self._guardrails.get(series_id)
        if guardrail is not None:
            return guardrail
        guardrail = IngestLoopGuardrail(enabled=True, config=self._config)
        self._guardrails[series_id] = guardrail
        return guardrail

    def drop(self, series_id: str) -> None:
        self._guardrails.pop(series_id, None)

    def clear(self) -> None:
        self._guardrails.clear()
