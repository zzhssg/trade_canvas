from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.core.schemas import FactorMetaV1, FactorSliceV1
from backend.app.factor.bundles.anchor import AnchorSlicePlugin
from backend.app.factor.slice_plugin_contract import FactorSliceBuildContext
from backend.app.factor.store import FactorHeadSnapshotRow
from backend.app.storage.candle_store import CandleStore


class AnchorSlicePluginTests(unittest.TestCase):
    def test_slice_keeps_stronger_current_candidate_from_head(self) -> None:
        plugin = AnchorSlicePlugin()
        series_id = "binance:spot:BTC/USDT:5m"
        pen_slice = FactorSliceV1(
            history={},
            head={
                "extending": {
                    "start_time": 100,
                    "end_time": 300,
                    "start_price": 10.0,
                    "end_price": 30.0,
                    "direction": 1,
                },
                "candidate": {
                    "start_time": 300,
                    "end_time": 350,
                    "start_price": 30.0,
                    "end_price": 25.0,
                    "direction": -1,
                },
            },
            meta=FactorMetaV1(
                series_id=series_id,
                at_time=500,
                candle_id=f"{series_id}:500",
                factor_name="pen",
            ),
        )
        anchor_head_row = FactorHeadSnapshotRow(
            id=1,
            series_id=series_id,
            factor_name="anchor",
            candle_time=500,
            seq=0,
            head={"current_anchor_ref": {"kind": "candidate", "start_time": 100, "end_time": 300, "direction": 1}},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = FactorSliceBuildContext(
                series_id=series_id,
                aligned_time=500,
                at_time=500,
                start_time=0,
                window_candles=2000,
                candle_id=f"{series_id}:500",
                candle_store=CandleStore(db_path=Path(tmpdir) / "candles.db"),
                buckets={
                    "pen_confirmed": [
                        {
                            "start_time": 40,
                            "end_time": 80,
                            "start_price": 9.0,
                            "end_price": 10.0,
                            "direction": 1,
                            "visible_time": 80,
                        }
                    ],
                    "anchor_switches": [
                        {
                            "switch_time": 400,
                            "new_anchor": {"kind": "candidate", "start_time": 100, "end_time": 300, "direction": 1},
                        }
                    ],
                },
                head_rows={"anchor": anchor_head_row},
                snapshots={"pen": pen_slice},
            )

            snapshot = plugin.build_snapshot(ctx)

        self.assertIsNotNone(snapshot)
        if snapshot is None:
            return
        current_ref = snapshot.head.get("current_anchor_ref")
        self.assertIsInstance(current_ref, dict)
        if not isinstance(current_ref, dict):
            return
        self.assertEqual(int(current_ref.get("start_time") or 0), 100)
        self.assertEqual(int(current_ref.get("end_time") or 0), 300)
        self.assertEqual(int(current_ref.get("direction") or 0), 1)


if __name__ == "__main__":
    unittest.main()
