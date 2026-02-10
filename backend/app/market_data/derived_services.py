from __future__ import annotations

from ..blocking import run_blocking
from ..derived_timeframes import (
    derived_base_timeframe,
    derived_enabled,
    is_derived_series_id,
    rollup_closed_candles,
    to_base_series_id,
)
from ..market_flags import derived_backfill_base_candles
from ..series_id import parse_series_id
from ..store import CandleStore


def build_derived_initial_backfill_handler(
    *,
    store: CandleStore,
    factor_orchestrator,
    overlay_orchestrator,
):
    async def _handler(*, series_id: str) -> None:
        if not derived_enabled() or not is_derived_series_id(series_id):
            return
        try:
            await run_blocking(_backfill_once, series_id)
        except Exception:
            return

    def _backfill_once(series_id: str) -> None:
        if store.head_time(series_id) is not None:
            return
        base_series_id = to_base_series_id(series_id)
        base_limit = derived_backfill_base_candles()

        base_candles = store.get_closed(base_series_id, since=None, limit=int(base_limit))
        if not base_candles:
            return
        derived_tf = parse_series_id(series_id).timeframe
        derived_closed = rollup_closed_candles(
            base_timeframe=derived_base_timeframe(),
            derived_timeframe=derived_tf,
            base_candles=base_candles,
        )
        if not derived_closed:
            return

        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, series_id, derived_closed)
            conn.commit()

        rebuilt = False
        try:
            factor_result = factor_orchestrator.ingest_closed(
                series_id=series_id,
                up_to_candle_time=int(derived_closed[-1].candle_time),
            )
            rebuilt = bool(getattr(factor_result, "rebuilt", False))
        except Exception:
            pass
        try:
            if rebuilt:
                overlay_orchestrator.reset_series(series_id=series_id)
            overlay_orchestrator.ingest_closed(
                series_id=series_id,
                up_to_candle_time=int(derived_closed[-1].candle_time),
            )
        except Exception:
            pass

    return _handler
