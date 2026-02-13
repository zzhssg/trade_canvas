from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import KernelStore, OverlayEventRow


@dataclass(frozen=True)
class AdapterResult:
    ok: bool
    reason: str | None
    ledger: dict[str, Any] | None
    entry_marker: OverlayEventRow | None


class SingleSourceAdapter:
    """
    Reads only from the persisted artifacts and enforces candle_id alignment.
    """

    def __init__(self, store: KernelStore) -> None:
        self._store = store

    def get_latest(self, conn, *, symbol: str, timeframe: str) -> AdapterResult:
        latest_candle_id = self._store.get_latest_candle_id(conn, symbol=symbol, timeframe=timeframe)
        latest_ledger = self._store.get_latest_ledger(conn, symbol=symbol, timeframe=timeframe)
        if latest_candle_id is None or latest_ledger is None:
            return AdapterResult(ok=False, reason="not_ready", ledger=None, entry_marker=None)

        if latest_ledger.candle_id != latest_candle_id:
            return AdapterResult(ok=False, reason="candle_id_mismatch", ledger=None, entry_marker=None)

        entry = self._store.get_latest_overlay_event(conn, symbol=symbol, timeframe=timeframe, kind="signal.entry")
        return AdapterResult(ok=True, reason=None, ledger=latest_ledger.payload, entry_marker=entry)

    def validate_strategy_alignment(self, *, strategy_last_candle_id: str, ledger_candle_id: str) -> bool:
        return strategy_last_candle_id == ledger_candle_id
