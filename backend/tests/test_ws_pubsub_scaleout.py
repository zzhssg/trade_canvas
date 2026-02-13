from __future__ import annotations

import asyncio
import unittest

from backend.app.schemas import CandleClosed
from backend.app.ws.hub import CandleHub
from backend.app.ws_publishers import WsPubsubConsumer, WsPubsubMessage


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


class _FakeBus:
    def __init__(self) -> None:
        self.subscribers: list[WsPubsubConsumer] = []
        self.published: list[WsPubsubMessage] = []

    def attach(self, consumer: WsPubsubConsumer) -> None:
        self.subscribers.append(consumer)

    def detach(self, consumer: WsPubsubConsumer) -> None:
        if consumer in self.subscribers:
            self.subscribers.remove(consumer)

    async def publish(self, message: WsPubsubMessage) -> None:
        self.published.append(message)
        for consumer in list(self.subscribers):
            await consumer(message)


class _FakePublisher:
    def __init__(self, *, bus: _FakeBus) -> None:
        self._bus = bus
        self._consumer: WsPubsubConsumer | None = None
        self._started = False

    def set_consumer(self, consumer: WsPubsubConsumer) -> None:
        self._consumer = consumer

    async def start(self) -> None:
        if self._started:
            return
        if self._consumer is None:
            raise RuntimeError("consumer_not_set")
        self._bus.attach(self._consumer)
        self._started = True

    async def publish(self, message: WsPubsubMessage) -> None:
        await self._bus.publish(message)

    async def close(self) -> None:
        if self._consumer is not None:
            self._bus.detach(self._consumer)
        self._started = False


class WsPubsubScaleoutTests(unittest.TestCase):
    def test_cross_instance_closed_publish_reaches_remote_subscriber(self) -> None:
        async def run() -> None:
            bus = _FakeBus()
            hub_a = CandleHub(
                publisher=_FakePublisher(bus=bus),
                instance_id="instance-a",
            )
            hub_b = CandleHub(
                publisher=_FakePublisher(bus=bus),
                instance_id="instance-b",
            )
            await hub_a.start_pubsub()
            await hub_b.start_pubsub()

            ws_b = _FakeWs()
            series_id = "binance:spot:BTC/USDT:1m"
            await hub_b.subscribe(ws_b, series_id=series_id, since=100, supports_batch=False)  # type: ignore[arg-type]

            await hub_a.publish_closed(series_id=series_id, candle=_candle(160))

            self.assertEqual(len(bus.published), 1)
            self.assertEqual([p.get("type") for p in ws_b.payloads], ["candle_closed"])
            self.assertEqual(int(ws_b.payloads[0]["candle"]["candle_time"]), 160)

            await hub_a.close_pubsub()
            await hub_b.close_pubsub()

        asyncio.run(run())

    def test_cross_instance_batch_publish_avoids_message_loop(self) -> None:
        async def run() -> None:
            bus = _FakeBus()
            hub_a = CandleHub(
                publisher=_FakePublisher(bus=bus),
                instance_id="instance-a",
            )
            hub_b = CandleHub(
                publisher=_FakePublisher(bus=bus),
                instance_id="instance-b",
            )
            await hub_a.start_pubsub()
            await hub_b.start_pubsub()

            ws_b = _FakeWs()
            series_id = "binance:spot:ETH/USDT:1m"
            await hub_b.subscribe(ws_b, series_id=series_id, since=None, supports_batch=True)  # type: ignore[arg-type]

            await hub_a.publish_closed_batch(
                series_id=series_id,
                candles=[_candle(100), _candle(160), _candle(220)],
            )

            self.assertEqual(len(bus.published), 1)
            self.assertEqual([p.get("type") for p in ws_b.payloads], ["candles_batch"])
            self.assertEqual(
                [int(c.get("candle_time") or 0) for c in ws_b.payloads[0].get("candles", [])],
                [100, 160, 220],
            )

            await hub_a.close_pubsub()
            await hub_b.close_pubsub()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
