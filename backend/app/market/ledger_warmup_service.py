from __future__ import annotations

from dataclasses import dataclass, field

from ..core.ports import DebugHubPort, ReadLedgerWarmupFlagsPort
from ..ledger.ports import LedgerSyncPreparePort
from .series_cooldown_slots import SeriesCooldownSlots


@dataclass(frozen=True)
class MarketLedgerWarmupService:
    runtime_flags: ReadLedgerWarmupFlagsPort
    debug_hub: DebugHubPort
    ledger_sync_service: LedgerSyncPreparePort
    warmup_cooldown_seconds: float = 2.0
    _warmup_slots: SeriesCooldownSlots = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_warmup_slots",
            SeriesCooldownSlots(cooldown_seconds=float(self.warmup_cooldown_seconds)),
        )

    def _enabled(self) -> bool:
        return bool(self.runtime_flags.enable_read_ledger_warmup)

    def ensure_ledgers_warm(self, *, series_id: str, store_head_time: int | None) -> None:
        if not self._enabled():
            return
        if store_head_time is None or int(store_head_time) <= 0:
            return
        target_time = int(store_head_time)
        if not self._warmup_slots.try_acquire_target(series_id=series_id, target_time=target_time):
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
            self._warmup_slots.release_target(series_id=series_id, target_time=int(target_time))
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
