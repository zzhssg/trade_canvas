from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from backend.app.core.schemas import CandleClosed
from backend.app.factor.orchestrator import FactorOrchestrator, FactorSettings
from backend.app.factor.store import FactorStore
from backend.app.factor.processor_sr import SrProcessor
from backend.app.factor.sr_component import SrParams, build_sr_snapshot
from backend.app.factor.pen import PivotMajorPoint
from backend.app.overlay.orchestrator import OverlayOrchestrator
from backend.app.overlay.store import OverlayStore
from backend.app.storage.candle_store import CandleStore


class _Candle:
    def __init__(self, *, candle_time: int, high: float, low: float, close: float) -> None:
        self.candle_time = int(candle_time)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)


def _closed_candle(*, candle_time: int, high: float, low: float, close: float) -> CandleClosed:
    return CandleClosed(
        candle_time=int(candle_time),
        open=float(close),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=10.0,
    )


def _candles() -> list[_Candle]:
    out: list[_Candle] = []
    base = 1_700_000_000
    for idx in range(40):
        high = 100.0
        low = 90.0
        close = 95.0
        if idx == 5:
            high = 110.0
            close = 100.0
        if idx == 15:
            high = 110.0
            close = 99.0
        out.append(_Candle(candle_time=base + idx * 60, high=high, low=low, close=close))
    return out


class SrFactorTests(unittest.TestCase):
    def test_build_sr_snapshot_with_two_major_resistance_pivots(self) -> None:
        candles = _candles()
        time_to_idx = {int(c.candle_time): idx for idx, c in enumerate(candles)}
        major_pivots = [
            {
                "pivot_time": candles[5].candle_time,
                "pivot_price": 110.0,
                "direction": "resistance",
                "visible_time": candles[8].candle_time,
                "pivot_idx": 5,
            },
            {
                "pivot_time": candles[15].candle_time,
                "pivot_price": 110.0,
                "direction": "resistance",
                "visible_time": candles[18].candle_time,
                "pivot_idx": 15,
            },
        ]

        snapshot = build_sr_snapshot(
            candles=candles,
            major_pivots=major_pivots,
            time_to_idx=time_to_idx,
            params=SrParams(max_levels=5),
        )
        levels = list(snapshot.get("levels") or [])
        self.assertGreaterEqual(len(levels), 1)
        self.assertEqual(str(levels[0].get("level_type")), "resistance")

    def test_sr_processor_emits_snapshot_event_when_new_major_arrives(self) -> None:
        processor = SrProcessor()
        candles = _candles()
        time_to_idx = {int(c.candle_time): idx for idx, c in enumerate(candles)}
        state = SimpleNamespace(
            visible_time=int(candles[8].candle_time),
            candles=candles,
            time_to_idx=time_to_idx,
            major_candidates=[
                PivotMajorPoint(
                    pivot_time=int(candles[5].candle_time),
                    pivot_price=110.0,
                    direction="resistance",
                    visible_time=int(candles[8].candle_time),
                    pivot_idx=5,
                )
            ],
            events=[],
            sr_major_pivots=[],
            sr_snapshot={},
        )

        processor.run_tick(series_id="binance:futures:BTC/USDT:1m", state=state, runtime=SimpleNamespace(anchor_processor=None))
        self.assertEqual(len(state.events), 1)
        self.assertEqual(str(state.events[0].kind), "sr.snapshot")

        state.visible_time = int(candles[18].candle_time)
        state.major_candidates = [
            PivotMajorPoint(
                pivot_time=int(candles[15].candle_time),
                pivot_price=110.0,
                direction="resistance",
                visible_time=int(candles[18].candle_time),
                pivot_idx=15,
            )
        ]
        processor.run_tick(series_id="binance:futures:BTC/USDT:1m", state=state, runtime=SimpleNamespace(anchor_processor=None))
        payload = dict(state.events[-1].payload or {})
        self.assertIn("levels", payload)

    def test_factor_and_overlay_pipeline_produces_sr_draw_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "sr_factor_pipeline.db"
            candle_store = CandleStore(db_path=db_path)
            factor_store = FactorStore(db_path=db_path)
            overlay_store = OverlayStore(db_path=db_path)
            factor_orchestrator = FactorOrchestrator(
                candle_store=candle_store,
                factor_store=factor_store,
                settings=FactorSettings(
                    pivot_window_major=1,
                    pivot_window_minor=1,
                    lookback_candles=200,
                    state_rebuild_event_limit=1000,
                ),
            )
            overlay_orchestrator = OverlayOrchestrator(
                candle_store=candle_store,
                factor_store=factor_store,
                overlay_store=overlay_store,
            )
            series_id = "binance:futures:BTC/USDT:1m"
            base = 1_700_100_000
            highs = [10.0, 11.0, 15.0, 11.0, 10.0, 11.0, 15.0, 11.0, 10.0]
            lows = [5.0] * len(highs)
            closes = [9.0, 10.0, 14.0, 10.0, 9.0, 10.0, 14.0, 10.0, 9.0]
            with candle_store.connect() as conn:
                candle_store.upsert_many_closed_in_conn(
                    conn,
                    series_id,
                    [
                        _closed_candle(
                            candle_time=base + idx * 60,
                            high=high,
                            low=lows[idx],
                            close=closes[idx],
                        )
                        for idx, high in enumerate(highs)
                    ],
                )
                conn.commit()

            factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=base + (len(highs) - 1) * 60)
            overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=base + (len(highs) - 1) * 60)

            sr_events = factor_store.get_events_between_times(
                series_id=series_id,
                factor_name="sr",
                start_candle_time=base,
                end_candle_time=base + (len(highs) - 1) * 60,
            )
            self.assertTrue(sr_events)

            defs = overlay_store.get_latest_defs_up_to_time(
                series_id=series_id,
                up_to_time=base + (len(highs) - 1) * 60,
            )
            sr_defs = [row for row in defs if str(row.payload.get("feature") or "").startswith("sr.")]
            self.assertTrue(sr_defs)


if __name__ == "__main__":
    unittest.main()
