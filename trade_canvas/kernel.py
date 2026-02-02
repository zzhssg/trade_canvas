from __future__ import annotations

from dataclasses import dataclass

from .store import SqliteStore
from .types import CandleClosed


@dataclass(frozen=True)
class KernelResult:
    ledger: dict
    overlay_events: list[tuple[str, dict]]  # (kind, payload)


class SmaCrossKernel:
    """
    Minimal, deterministic "factor-kernel" for E2E:
    - Consumes only CandleClosed
    - Incremental update (rolling SMA)
    - Produces ledger + overlay marker on signal
    """

    def __init__(self, store: SqliteStore, *, fast: int = 5, slow: int = 20) -> None:
        if fast <= 0 or slow <= 0 or fast >= slow:
            raise ValueError("Require 0 < fast < slow")
        self._store = store
        self._fast = fast
        self._slow = slow
        self._state_prefix = f"sma_cross_v1:{fast}:{slow}"

    def apply_closed(self, conn, candle: CandleClosed) -> KernelResult:
        state_key = f"{self._state_prefix}:{candle.symbol}:{candle.timeframe}"
        state = self._store.load_state(conn, key=state_key) or {
            "fast_sum": 0.0,
            "slow_sum": 0.0,
            "fast_window": [],
            "slow_window": [],
            "prev_fast": None,
            "prev_slow": None,
        }

        def push(window_key: str, sum_key: str, size: int, value: float) -> None:
            window = list(state[window_key])
            total = float(state[sum_key])
            window.append(value)
            total += value
            if len(window) > size:
                total -= float(window.pop(0))
            state[window_key] = window
            state[sum_key] = total

        close = float(candle.close)
        push("fast_window", "fast_sum", self._fast, close)
        push("slow_window", "slow_sum", self._slow, close)

        fast_sma = None
        slow_sma = None
        if len(state["fast_window"]) == self._fast:
            fast_sma = float(state["fast_sum"]) / self._fast
        if len(state["slow_window"]) == self._slow:
            slow_sma = float(state["slow_sum"]) / self._slow

        signal = None
        overlay_events: list[tuple[str, dict]] = []

        prev_fast = state.get("prev_fast")
        prev_slow = state.get("prev_slow")
        if fast_sma is not None and slow_sma is not None and prev_fast is not None and prev_slow is not None:
            if prev_fast <= prev_slow and fast_sma > slow_sma:
                signal = {
                    "type": "OPEN_LONG",
                    "candle_id": candle.candle_id,
                    "time": candle.open_time,
                    "price": close,
                }
                overlay_events.append(
                    (
                        "signal.entry",
                        {
                            "candle_id": candle.candle_id,
                            "time": candle.open_time,
                            "price": close,
                            "label": "ENTRY",
                        },
                    )
                )

        # Update prev values after signal calculation.
        state["prev_fast"] = fast_sma
        state["prev_slow"] = slow_sma

        ledger = {
            "candle_id": candle.candle_id,
            "time": candle.open_time,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "features": {
                f"sma_{self._fast}": fast_sma,
                f"sma_{self._slow}": slow_sma,
            },
            "signal": signal,
        }

        # Persist minimal plot points for low-latency chart updates.
        if fast_sma is not None:
            self._store.upsert_plot_point(
                conn,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                feature_key=f"sma_{self._fast}",
                candle_id=candle.candle_id,
                candle_time=candle.open_time,
                value=float(fast_sma),
            )
        if slow_sma is not None:
            self._store.upsert_plot_point(
                conn,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                feature_key=f"sma_{self._slow}",
                candle_id=candle.candle_id,
                candle_time=candle.open_time,
                value=float(slow_sma),
            )

        self._store.save_state(conn, key=state_key, payload=state)
        self._store.set_latest_ledger(
            conn,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            candle_id=candle.candle_id,
            candle_time=candle.open_time,
            payload=ledger,
        )
        for kind, payload in overlay_events:
            self._store.append_overlay_event(
                conn,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                candle_id=candle.candle_id,
                candle_time=candle.open_time,
                kind=kind,
                payload=payload,
            )
        conn.commit()
        return KernelResult(ledger=ledger, overlay_events=overlay_events)
