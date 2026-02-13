from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.factor.store import FactorEventWrite, FactorStore
from backend.app.overlay.orchestrator import OverlayOrchestrator
from backend.app.overlay.store import OverlayStore
from backend.app.core.schemas import CandleClosed
from backend.app.storage.candle_store import CandleStore


def _candle(candle_time: int, *, close: float) -> CandleClosed:
    base = float(close)
    return CandleClosed(
        candle_time=int(candle_time),
        open=base,
        high=base + 1.0,
        low=base - 1.0,
        close=base,
        volume=10.0,
    )


class OverlayOrchestratorIntegrationTests(unittest.TestCase):
    def test_factor_events_drive_stable_overlay_defs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "overlay_integration.db"
            candle_store = CandleStore(db_path=db_path)
            factor_store = FactorStore(db_path=db_path)
            overlay_store = OverlayStore(db_path=db_path)
            orchestrator = OverlayOrchestrator(
                candle_store=candle_store,
                factor_store=factor_store,
                overlay_store=overlay_store,
            )
            series_id = "binance:futures:BTC/USDT:1m"

            with candle_store.connect() as conn:
                candle_store.upsert_many_closed_in_conn(
                    conn,
                    series_id,
                    [
                        _candle(120, close=10.0),
                        _candle(180, close=11.0),
                        _candle(240, close=12.0),
                    ],
                )
                conn.commit()

            with factor_store.connect() as conn:
                factor_store.insert_events_in_conn(
                    conn,
                    events=[
                        FactorEventWrite(
                            series_id=series_id,
                            factor_name="pivot",
                            candle_time=180,
                            kind="pivot.major",
                            event_key="major:120:resistance:5",
                            payload={
                                "pivot_time": 120,
                                "visible_time": 180,
                                "direction": "resistance",
                                "window": 5,
                            },
                        ),
                        FactorEventWrite(
                            series_id=series_id,
                            factor_name="pen",
                            candle_time=240,
                            kind="pen.confirmed",
                            event_key="confirmed:120:180:1",
                            payload={
                                "start_time": 120,
                                "end_time": 180,
                                "start_price": 10.0,
                                "end_price": 11.0,
                                "direction": 1,
                                "visible_time": 240,
                            },
                        ),
                        FactorEventWrite(
                            series_id=series_id,
                            factor_name="anchor",
                            candle_time=240,
                            kind="anchor.switch",
                            event_key="strong_pen:240:confirmed:120:180:1",
                            payload={
                                "switch_time": 240,
                                "visible_time": 240,
                                "reason": "strong_pen",
                                "new_anchor": {
                                    "kind": "confirmed",
                                    "start_time": 120,
                                    "end_time": 180,
                                    "direction": 1,
                                },
                            },
                        ),
                    ],
                )
                factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=240)
                conn.commit()

            orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=240)

            rows = overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=240)
            defs_by_id = {row.instruction_id: row.payload for row in rows}
            self.assertIn("pivot.major:120:resistance:5", defs_by_id)
            self.assertIn("pen.confirmed", defs_by_id)
            self.assertIn("anchor.current", defs_by_id)

            pen_payload = defs_by_id["pen.confirmed"]
            self.assertEqual(str(pen_payload.get("feature")), "pen.confirmed")
            pen_points = pen_payload.get("points") or []
            self.assertEqual(
                [(int(p.get("time") or 0), float(p.get("value") or 0.0)) for p in pen_points],
                [(120, 10.0), (180, 11.0)],
            )

            anchor_payload = defs_by_id["anchor.current"]
            self.assertEqual(str(anchor_payload.get("feature")), "anchor.current")
            anchor_points = anchor_payload.get("points") or []
            self.assertEqual(
                [(int(p.get("time") or 0), float(p.get("value") or 0.0)) for p in anchor_points],
                [(120, 10.0), (180, 11.0)],
            )
            self.assertEqual(int(overlay_store.head_time(series_id) or 0), 240)

            version_after_first_ingest = int(overlay_store.last_version_id(series_id))
            orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=240)
            version_after_second_ingest = int(overlay_store.last_version_id(series_id))
            self.assertEqual(version_after_second_ingest, version_after_first_ingest)


if __name__ == "__main__":
    unittest.main()
