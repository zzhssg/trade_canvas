from __future__ import annotations

import asyncio
import unittest

from backend.app.core.schemas import CandleClosed
from backend.app.ws.hub import CandleHub
from backend.app.ws.protocol import WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLES_BATCH, WS_MSG_GAP


def _candle(candle_time: int) -> CandleClosed:
    return CandleClosed(
        candle_time=int(candle_time),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
    )


class _FakeWs:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.payloads.append(dict(payload))

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        _ = code
        _ = reason


class WsHubDeliveryTests(unittest.TestCase):
    def test_publish_closed_batch_prefers_batch_payload_when_supported(self) -> None:
        async def run() -> None:
            hub = CandleHub()
            ws = _FakeWs()
            series_id = "binance:spot:BTC/USDT:1m"
            await hub.subscribe(ws, series_id=series_id, since=None, supports_batch=True)  # type: ignore[arg-type]

            await hub.publish_closed_batch(series_id=series_id, candles=[_candle(100), _candle(160)])

            self.assertEqual([p.get("type") for p in ws.payloads], [WS_MSG_CANDLES_BATCH])
            payload = ws.payloads[0]
            candles = payload.get("candles") or []
            self.assertEqual([int(item.get("candle_time") or 0) for item in candles], [100, 160])
            last_sent = await hub.get_last_sent(ws, series_id=series_id)  # type: ignore[arg-type]
            self.assertEqual(int(last_sent or 0), 160)

        asyncio.run(run())

    def test_publish_closed_batch_stream_emits_single_gap_then_closed(self) -> None:
        async def run() -> None:
            hub = CandleHub()
            ws = _FakeWs()
            series_id = "binance:spot:BTC/USDT:1m"
            await hub.subscribe(ws, series_id=series_id, since=100, supports_batch=False)  # type: ignore[arg-type]

            await hub.publish_closed_batch(series_id=series_id, candles=[_candle(280)])

            self.assertEqual([p.get("type") for p in ws.payloads], [WS_MSG_GAP, WS_MSG_CANDLE_CLOSED])
            gap = ws.payloads[0]
            self.assertEqual(int(gap.get("expected_next_time") or 0), 160)
            self.assertEqual(int(gap.get("actual_time") or 0), 280)
            last_sent = await hub.get_last_sent(ws, series_id=series_id)  # type: ignore[arg-type]
            self.assertEqual(int(last_sent or 0), 280)

        asyncio.run(run())

    def test_publish_closed_with_gap_backfill_recovers_before_live_candle(self) -> None:
        async def run() -> None:
            async def gap_backfill_handler(series_id: str, expected_next_time: int, actual_time: int) -> list[CandleClosed]:
                _ = series_id
                self.assertEqual(int(expected_next_time), 160)
                self.assertEqual(int(actual_time), 280)
                return [_candle(160), _candle(220)]

            hub = CandleHub(gap_backfill_handler=gap_backfill_handler)
            ws = _FakeWs()
            series_id = "binance:spot:BTC/USDT:1m"
            await hub.subscribe(ws, series_id=series_id, since=100, supports_batch=False)  # type: ignore[arg-type]

            await hub.publish_closed(series_id=series_id, candle=_candle(280))

            self.assertEqual([p.get("type") for p in ws.payloads], [WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLE_CLOSED])
            self.assertEqual([int(p.get("candle", {}).get("candle_time") or 0) for p in ws.payloads], [160, 220, 280])
            last_sent = await hub.get_last_sent(ws, series_id=series_id)  # type: ignore[arg-type]
            self.assertEqual(int(last_sent or 0), 280)

        asyncio.run(run())

    def test_publish_closed_keeps_single_candle_payload_even_when_supports_batch(self) -> None:
        async def run() -> None:
            hub = CandleHub()
            ws = _FakeWs()
            series_id = "binance:spot:BTC/USDT:1m"
            await hub.subscribe(ws, series_id=series_id, since=None, supports_batch=True)  # type: ignore[arg-type]

            await hub.publish_closed(series_id=series_id, candle=_candle(100))

            self.assertEqual([p.get("type") for p in ws.payloads], [WS_MSG_CANDLE_CLOSED])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
