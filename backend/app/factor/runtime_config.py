from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FactorSettings:
    pivot_window_major: int = 50
    pivot_window_minor: int = 5
    lookback_candles: int = 20000
    state_rebuild_event_limit: int = 50000


@dataclass(frozen=True)
class FactorOrchestratorRuntimeConfig:
    settings: FactorSettings
    ingest_enabled: bool
    fingerprint_rebuild_enabled: bool
    rebuild_keep_candles: int
    logic_version_override: str


class FactorRuntimeFlagsLike(Protocol):
    @property
    def factor_pivot_window_major(self) -> int: ...

    @property
    def factor_pivot_window_minor(self) -> int: ...

    @property
    def factor_lookback_candles(self) -> int: ...

    @property
    def factor_state_rebuild_event_limit(self) -> int: ...

    @property
    def enable_factor_ingest(self) -> bool: ...

    @property
    def enable_factor_fingerprint_rebuild(self) -> bool: ...

    @property
    def factor_rebuild_keep_candles(self) -> int: ...

    @property
    def factor_logic_version_override(self) -> str | None: ...


def build_factor_orchestrator_runtime_config(*, runtime_flags: FactorRuntimeFlagsLike) -> FactorOrchestratorRuntimeConfig:
    settings = FactorSettings(
        pivot_window_major=int(runtime_flags.factor_pivot_window_major),
        pivot_window_minor=int(runtime_flags.factor_pivot_window_minor),
        lookback_candles=int(runtime_flags.factor_lookback_candles),
        state_rebuild_event_limit=int(runtime_flags.factor_state_rebuild_event_limit),
    )
    return FactorOrchestratorRuntimeConfig(
        settings=settings,
        ingest_enabled=bool(runtime_flags.enable_factor_ingest),
        fingerprint_rebuild_enabled=bool(runtime_flags.enable_factor_fingerprint_rebuild),
        rebuild_keep_candles=int(runtime_flags.factor_rebuild_keep_candles),
        logic_version_override=str(runtime_flags.factor_logic_version_override or ""),
    )
