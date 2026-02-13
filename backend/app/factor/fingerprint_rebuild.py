from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .store import FactorStore
from ..storage.candle_store import CandleStore


class _DebugHubLike(Protocol):
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


@dataclass(frozen=True)
class FactorFingerprintRebuildOutcome:
    forced: bool
    keep_candles: int | None = None
    trimmed_rows: int = 0


class FactorFingerprintRebuildCoordinator:
    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        debug_hub: _DebugHubLike | None = None,
        keep_candles: int = 2000,
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._debug_hub = debug_hub
        self._keep_candles = max(100, int(keep_candles))

    def _emit_rebuild_event(
        self,
        *,
        series_id: str,
        fingerprint: str,
        keep_candles: int,
        trimmed_rows: int,
    ) -> None:
        if self._debug_hub is None:
            return
        self._debug_hub.emit(
            pipe="write",
            event="factor.fingerprint.rebuild",
            message="fingerprint mismatch, cleared factor data and rebuilding from kept candles",
            series_id=series_id,
            data={
                "series_id": str(series_id),
                "fingerprint": str(fingerprint),
                "keep_candles": int(keep_candles),
                "trimmed_rows": int(trimmed_rows),
            },
        )

    def ensure_series_ready(
        self,
        *,
        series_id: str,
        auto_rebuild: bool,
        current_fingerprint: str,
    ) -> FactorFingerprintRebuildOutcome:
        if not bool(auto_rebuild):
            return FactorFingerprintRebuildOutcome(forced=False)

        current = self._factor_store.get_series_fingerprint(series_id)
        if current is not None and str(current.fingerprint) == str(current_fingerprint):
            return FactorFingerprintRebuildOutcome(forced=False)

        keep_candles = int(self._keep_candles)
        trimmed_rows = 0
        with self._candle_store.connect() as conn:
            trimmed_rows = self._candle_store.trim_series_to_latest_n_in_conn(
                conn,
                series_id=series_id,
                keep=int(keep_candles),
            )
            conn.commit()

        with self._factor_store.connect() as conn:
            self._factor_store.clear_series_in_conn(conn, series_id=series_id)
            self._factor_store.upsert_series_fingerprint_in_conn(
                conn,
                series_id=series_id,
                fingerprint=current_fingerprint,
            )
            conn.commit()

        self._emit_rebuild_event(
            series_id=series_id,
            fingerprint=current_fingerprint,
            keep_candles=int(keep_candles),
            trimmed_rows=int(trimmed_rows),
        )
        return FactorFingerprintRebuildOutcome(
            forced=True,
            keep_candles=int(keep_candles),
            trimmed_rows=int(trimmed_rows),
        )
