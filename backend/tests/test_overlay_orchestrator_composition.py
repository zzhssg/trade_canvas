from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.app.factor.store import FactorStore
from backend.app.overlay.ingest_reader import OverlayIngestInput
from backend.app.overlay.orchestrator import OverlayOrchestrator, OverlaySettings
from backend.app.overlay.store import OverlayStore
from backend.app.core.schemas import CandleClosed
from backend.app.storage.candle_store import CandleStore


def _candle(candle_time: int, *, close: float) -> CandleClosed:
    return CandleClosed(
        candle_time=int(candle_time),
        open=float(close),
        high=float(close) + 1.0,
        low=float(close) - 1.0,
        close=float(close),
        volume=10.0,
    )


class _FakeReader:
    def __init__(self, ingest_input: OverlayIngestInput) -> None:
        self._ingest_input = ingest_input
        self.calls: list[dict[str, int | str]] = []

    def read(
        self,
        *,
        series_id: str,
        to_time: int,
        tf_s: int,
        window_candles: int,
    ) -> OverlayIngestInput:
        self.calls.append(
            {
                "series_id": str(series_id),
                "to_time": int(to_time),
                "tf_s": int(tf_s),
                "window_candles": int(window_candles),
            }
        )
        return self._ingest_input


class _FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def persist(
        self,
        *,
        series_id: str,
        to_time: int,
        marker_defs: list[tuple[str, str, int, dict[str, Any]]],
        polyline_defs: list[tuple[str, int, dict[str, Any]]],
    ) -> int:
        self.calls.append(
            {
                "series_id": str(series_id),
                "to_time": int(to_time),
                "marker_defs": list(marker_defs),
                "polyline_defs": list(polyline_defs),
            }
        )
        return 7


class OverlayOrchestratorCompositionTests(unittest.TestCase):
    def test_orchestrator_uses_injected_reader_and_writer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "overlay_compose.db"
            series_id = "binance:futures:BTC/USDT:1m"
            ingest_input = OverlayIngestInput(
                to_time=240,
                cutoff_time=60,
                window_candles=2000,
                factor_rows=[],
                buckets={
                    "pivot_major": [
                        {
                            "pivot_time": 120,
                            "visible_time": 180,
                            "direction": "resistance",
                            "window": 5,
                        }
                    ],
                    "pivot_minor": [],
                    "pen_confirmed": [
                        {
                            "start_time": 120,
                            "end_time": 180,
                            "start_price": 10.0,
                            "end_price": 11.0,
                            "direction": 1,
                            "visible_time": 240,
                        }
                    ],
                    "zhongshu_dead": [],
                    "anchor_switches": [],
                },
                candles=[
                    _candle(120, close=10.0),
                    _candle(180, close=11.0),
                    _candle(240, close=12.0),
                ],
            )
            fake_reader = _FakeReader(ingest_input)
            fake_writer = _FakeWriter()
            orchestrator = OverlayOrchestrator(
                candle_store=CandleStore(db_path=db_path),
                factor_store=FactorStore(db_path=db_path),
                overlay_store=OverlayStore(db_path=db_path),
                ingest_reader=fake_reader,
                instruction_writer=fake_writer,
            )

            orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=240)

            self.assertEqual(len(fake_reader.calls), 1)
            self.assertEqual(fake_reader.calls[0]["series_id"], series_id)
            self.assertEqual(int(fake_reader.calls[0]["to_time"] or 0), 240)
            self.assertEqual(len(fake_writer.calls), 1)
            self.assertEqual(fake_writer.calls[0]["series_id"], series_id)
            marker_ids = [str(row[0]) for row in fake_writer.calls[0]["marker_defs"]]
            polyline_ids = [str(row[0]) for row in fake_writer.calls[0]["polyline_defs"]]
            self.assertIn("pivot.major:120:resistance:5", marker_ids)
            self.assertIn("pen.confirmed", polyline_ids)

    def test_orchestrator_skips_injected_io_when_ingest_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "overlay_disabled.db"
            fake_reader = _FakeReader(
                OverlayIngestInput(
                    to_time=240,
                    cutoff_time=60,
                    window_candles=2000,
                    factor_rows=[],
                    buckets={},
                    candles=[],
                )
            )
            fake_writer = _FakeWriter()
            orchestrator = OverlayOrchestrator(
                candle_store=CandleStore(db_path=db_path),
                factor_store=FactorStore(db_path=db_path),
                overlay_store=OverlayStore(db_path=db_path),
                settings=OverlaySettings(ingest_enabled=False, window_candles=2000),
                ingest_reader=fake_reader,
                instruction_writer=fake_writer,
            )

            orchestrator.ingest_closed(series_id="binance:futures:BTC/USDT:1m", up_to_candle_time=240)

            self.assertEqual(fake_reader.calls, [])
            self.assertEqual(fake_writer.calls, [])


if __name__ == "__main__":
    unittest.main()
