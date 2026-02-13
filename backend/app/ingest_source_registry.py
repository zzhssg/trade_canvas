from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .ingest_job_runner import IngestLoopFn


@dataclass(frozen=True)
class IngestSourceBinding:
    source: str
    get_ingest_fn: Callable[[], IngestLoopFn]


class IngestSourceRegistry:
    def __init__(self, *, bindings: Mapping[str, IngestSourceBinding]) -> None:
        self._bindings = {str(exchange).strip().lower(): binding for exchange, binding in bindings.items()}

    def resolve(self, *, exchange: str) -> IngestSourceBinding:
        normalized = str(exchange).strip().lower()
        binding = self._bindings.get(normalized)
        if binding is None:
            raise ValueError(f"unsupported exchange for realtime ingest: {exchange!r}")
        return binding
