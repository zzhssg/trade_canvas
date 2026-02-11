from __future__ import annotations

from typing import Mapping, Protocol


class AlignedStorePort(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class HeadStorePort(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class PipelineStepPort(Protocol):
    @property
    def name(self) -> str: ...


class RefreshResultPort(Protocol):
    @property
    def steps(self) -> tuple[PipelineStepPort, ...] | list[PipelineStepPort]: ...


class IngestPipelineSyncPort(Protocol):
    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]) -> RefreshResultPort: ...


class DebugHubPort(Protocol):
    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None: ...
