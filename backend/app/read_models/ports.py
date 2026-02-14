from __future__ import annotations

from typing import Protocol

from ..core.ports import HeadStorePort, OverlayOrchestratorPort
from ..core.schemas import DrawDeltaV1, GetFactorSlicesResponseV1
from ..overlay.store import OverlayInstructionVersionRow


class OverlayStoreReadPort(HeadStorePort, Protocol):
    def get_latest_defs_up_to_time(self, *, series_id: str, up_to_time: int) -> list[OverlayInstructionVersionRow]: ...

    def get_patch_after_version(
        self,
        *,
        series_id: str,
        after_version_id: int,
        up_to_time: int,
        limit: int = 50000,
    ) -> list[OverlayInstructionVersionRow]: ...

    def last_version_id(self, series_id: str) -> int: ...


class FactorReadServicePort(Protocol):
    @property
    def strict_mode(self) -> bool: ...

    def read_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
    ) -> GetFactorSlicesResponseV1: ...


class DrawReadServicePort(Protocol):
    def read_delta(
        self,
        *,
        series_id: str,
        cursor_version_id: int,
        window_candles: int,
        at_time: int | None = None,
    ) -> DrawDeltaV1: ...


OverlayOrchestratorReadPort = OverlayOrchestratorPort
