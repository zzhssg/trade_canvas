from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol

from ..core.ports import DebugHubPort


class _RuntimeFlagsLike(Protocol):
    @property
    def enable_read_ledger_warmup(self) -> bool: ...

    @property
    def enable_debug_api(self) -> bool: ...


class _LedgerRefreshOutcomeLike(Protocol):
    @property
    def refreshed(self) -> bool: ...

    @property
    def step_names(self) -> tuple[str, ...]: ...

    @property
    def factor_head_time(self) -> int | None: ...

    @property
    def overlay_head_time(self) -> int | None: ...


class _LedgerHeadSnapshotLike(Protocol):
    @property
    def factor_head_time(self) -> int | None: ...

    @property
    def overlay_head_time(self) -> int | None: ...


class _LedgerSyncLike(Protocol):
    def head_snapshot(self, *, series_id: str) -> _LedgerHeadSnapshotLike: ...

    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> _LedgerRefreshOutcomeLike: ...


@dataclass(frozen=True)
class MarketLedgerWarmupService:
    runtime_flags: _RuntimeFlagsLike
    debug_hub: DebugHubPort
    ledger_sync_service: _LedgerSyncLike
    warmup_cooldown_seconds: float = 2.0
    _warmup_guard_lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
    _warmup_guard_state: dict[str, tuple[bool, int, float]] = field(default_factory=dict, init=False, repr=False, compare=False)

    def _enabled(self) -> bool:
        return bool(self.runtime_flags.enable_read_ledger_warmup)

    def _try_acquire_warmup_slot(self, *, series_id: str, target_time: int) -> bool:
        cooldown = max(0.1, float(self.warmup_cooldown_seconds))
        now = float(time.monotonic())
        with self._warmup_guard_lock:
            in_flight, last_target_time, last_run = self._warmup_guard_state.get(series_id, (False, 0, 0.0))
            if bool(in_flight):
                return False
            same_or_older_target = int(target_time) <= int(last_target_time)
            if same_or_older_target and (now - float(last_run) < cooldown):
                return False
            self._warmup_guard_state[series_id] = (True, max(int(last_target_time), int(target_time)), now)
            return True

    def _release_warmup_slot(self, *, series_id: str, target_time: int) -> None:
        now = float(time.monotonic())
        with self._warmup_guard_lock:
            _, last_target_time, _ = self._warmup_guard_state.get(series_id, (False, 0, 0.0))
            self._warmup_guard_state[series_id] = (False, max(int(last_target_time), int(target_time)), now)

    def ensure_ledgers_warm(self, *, series_id: str, store_head_time: int | None) -> None:
        if not self._enabled():
            return
        if store_head_time is None or int(store_head_time) <= 0:
            return
        target_time = int(store_head_time)
        if not self._try_acquire_warmup_slot(series_id=series_id, target_time=target_time):
            return
        step_names: list[str] = []
        err: Exception | None = None
        ledger_sync = self.ledger_sync_service
        snapshot = ledger_sync.head_snapshot(series_id=series_id)
        factor_head_before = None if snapshot.factor_head_time is None else int(snapshot.factor_head_time)
        overlay_head_before = None if snapshot.overlay_head_time is None else int(snapshot.overlay_head_time)
        factor_head_after = factor_head_before
        overlay_head_after = overlay_head_before
        try:
            refresh = ledger_sync.refresh_if_needed(
                series_id=series_id,
                up_to_time=int(target_time),
            )
            step_names = list(refresh.step_names)
            factor_head_after = None if refresh.factor_head_time is None else int(refresh.factor_head_time)
            overlay_head_after = None if refresh.overlay_head_time is None else int(refresh.overlay_head_time)
        except Exception as exc:
            err = exc
        finally:
            self._release_warmup_slot(series_id=series_id, target_time=int(target_time))
        if bool(self.runtime_flags.enable_debug_api):
            payload: dict[str, object] = {
                "target_time": int(target_time),
                "factor_head_before": None if factor_head_before is None else int(factor_head_before),
                "overlay_head_before": None if overlay_head_before is None else int(overlay_head_before),
                "factor_head_after": None if factor_head_after is None else int(factor_head_after),
                "overlay_head_after": None if overlay_head_after is None else int(overlay_head_after),
                "steps": step_names,
            }
            if err is not None:
                payload["error"] = str(err)
            self.debug_hub.emit(
                pipe="read",
                event="read.http.market_candles_ledger_warmup",
                level="warn" if err is not None else "info",
                series_id=series_id,
                message="ensure factor/overlay ledgers are warm",
                data=payload,
            )
