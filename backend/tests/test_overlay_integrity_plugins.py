from __future__ import annotations

import unittest

from backend.app.overlay.integrity_plugins import (
    AnchorCurrentStartIntegrityPlugin,
    OverlayIntegrityContext,
    ZhongshuSignatureIntegrityPlugin,
    evaluate_overlay_integrity,
)
from backend.app.overlay.store import OverlayInstructionVersionRow
from backend.app.core.schemas import FactorMetaV1, FactorSliceV1, GetFactorSlicesResponseV1


def _meta(*, factor_name: str, at_time: int = 180) -> FactorMetaV1:
    return FactorMetaV1(
        series_id="binance:futures:BTC/USDT:1m",
        at_time=int(at_time),
        candle_id=f"binance:futures:BTC/USDT:1m:{int(at_time)}",
        factor_name=factor_name,
    )


def _row(*, instruction_id: str, kind: str, payload: dict) -> OverlayInstructionVersionRow:
    return OverlayInstructionVersionRow(
        version_id=1,
        series_id="binance:futures:BTC/USDT:1m",
        instruction_id=instruction_id,
        kind=kind,
        visible_time=180,
        payload=payload,
    )


class OverlayIntegrityPluginTests(unittest.TestCase):
    def test_anchor_current_start_plugin_detects_mismatch(self) -> None:
        plugin = AnchorCurrentStartIntegrityPlugin()
        slices = GetFactorSlicesResponseV1(
            series_id="binance:futures:BTC/USDT:1m",
            at_time=180,
            candle_id="binance:futures:BTC/USDT:1m:180",
            factors=["anchor"],
            snapshots={
                "anchor": FactorSliceV1(
                    history={},
                    head={"current_anchor_ref": {"kind": "confirmed", "start_time": 120, "end_time": 180, "direction": 1}},
                    meta=_meta(factor_name="anchor"),
                )
            },
        )
        result = plugin.evaluate(
            ctx=OverlayIntegrityContext(
                series_id="binance:futures:BTC/USDT:1m",
                slices=slices,
                latest_defs=[
                    _row(
                        instruction_id="anchor.current",
                        kind="polyline",
                        payload={"points": [{"time": 60, "value": 1.0}, {"time": 180, "value": 2.0}]},
                    )
                ],
            )
        )
        self.assertTrue(result.should_rebuild)

    def test_zhongshu_signature_plugin_detects_bogus_id(self) -> None:
        plugin = ZhongshuSignatureIntegrityPlugin()
        slices = GetFactorSlicesResponseV1(
            series_id="binance:futures:BTC/USDT:1m",
            at_time=180,
            candle_id="binance:futures:BTC/USDT:1m:180",
            factors=["zhongshu"],
            snapshots={
                "zhongshu": FactorSliceV1(
                    history={"dead": [{"start_time": 120, "end_time": 180, "zg": 11.0, "zd": 9.0}]},
                    head={},
                    meta=_meta(factor_name="zhongshu"),
                )
            },
        )
        result = plugin.evaluate(
            ctx=OverlayIntegrityContext(
                series_id="binance:futures:BTC/USDT:1m",
                slices=slices,
                latest_defs=[
                    _row(
                        instruction_id="zhongshu.dead:bogus:top",
                        kind="polyline",
                        payload={"points": [{"time": 1, "value": 1.0}, {"time": 2, "value": 1.0}]},
                    )
                ],
            )
        )
        self.assertTrue(result.should_rebuild)

    def test_evaluate_overlay_integrity_passes_when_signatures_match(self) -> None:
        slices = GetFactorSlicesResponseV1(
            series_id="binance:futures:BTC/USDT:1m",
            at_time=180,
            candle_id="binance:futures:BTC/USDT:1m:180",
            factors=["anchor", "zhongshu"],
            snapshots={
                "anchor": FactorSliceV1(
                    history={},
                    head={"current_anchor_ref": {"kind": "confirmed", "start_time": 120, "end_time": 180, "direction": 1}},
                    meta=_meta(factor_name="anchor"),
                ),
                "zhongshu": FactorSliceV1(
                    history={"dead": [{"start_time": 120, "end_time": 180, "zg": 11.0, "zd": 9.0}]},
                    head={},
                    meta=_meta(factor_name="zhongshu"),
                ),
            },
        )
        latest_defs = [
            _row(
                instruction_id="anchor.current",
                kind="polyline",
                payload={"points": [{"time": 120, "value": 1.0}, {"time": 180, "value": 2.0}]},
            ),
            _row(
                instruction_id="zhongshu.dead:120:180:11.000000:9.000000:top",
                kind="polyline",
                payload={"points": [{"time": 120, "value": 11.0}, {"time": 180, "value": 11.0}]},
            ),
            _row(
                instruction_id="zhongshu.dead:120:180:11.000000:9.000000:bottom",
                kind="polyline",
                payload={"points": [{"time": 120, "value": 9.0}, {"time": 180, "value": 9.0}]},
            ),
        ]
        should_rebuild, details = evaluate_overlay_integrity(
            series_id="binance:futures:BTC/USDT:1m",
            slices=slices,
            latest_defs=latest_defs,
        )
        self.assertFalse(should_rebuild)
        self.assertTrue(details)


if __name__ == "__main__":
    unittest.main()
