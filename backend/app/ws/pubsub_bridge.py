from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..core.schemas import CandleClosed
from ..ws_publishers import WsPublisher, WsPubsubEventType, WsPubsubMessage

logger = logging.getLogger(__name__)


_OnClosed = Callable[[str, CandleClosed], Awaitable[None]]
_OnBatch = Callable[[str, list[CandleClosed]], Awaitable[None]]
_OnForming = Callable[[str, CandleClosed], Awaitable[None]]
_OnSystem = Callable[[str, str, str, dict[str, object]], Awaitable[None]]


@dataclass(frozen=True)
class WsPubsubCallbacks:
    on_closed: _OnClosed
    on_batch: _OnBatch
    on_forming: _OnForming
    on_system: _OnSystem


class WsPubsubBridge:
    def __init__(
        self,
        *,
        publisher: WsPublisher | None,
        callbacks: WsPubsubCallbacks,
        instance_id: str | None = None,
    ) -> None:
        self._publisher = publisher
        self._callbacks = callbacks
        self._instance_id = str(instance_id or "").strip() or uuid.uuid4().hex
        self._started = False
        if publisher is not None:
            publisher.set_consumer(self.consume)

    async def start(self) -> None:
        publisher = self._publisher
        if publisher is None or bool(self._started):
            return
        await publisher.start()
        self._started = True

    async def close(self) -> None:
        publisher = self._publisher
        if publisher is None:
            return
        try:
            await publisher.close()
        finally:
            self._started = False

    async def publish(
        self,
        *,
        series_id: str,
        event_type: WsPubsubEventType,
        payload: dict[str, object],
    ) -> None:
        publisher = self._publisher
        if publisher is None:
            return
        try:
            message = WsPubsubMessage(
                source=str(self._instance_id),
                series_id=str(series_id),
                event_type=event_type,
                payload=dict(payload),
            )
            await publisher.publish(message)
        except Exception:
            logger.exception("market_ws_pubsub_publish_failed event=%s series_id=%s", event_type, series_id)

    async def consume(self, message: WsPubsubMessage) -> None:
        if str(message.source) == str(self._instance_id):
            return
        event_type = str(message.event_type)
        if event_type == "candle_closed":
            candle_raw = message.payload.get("candle")
            if not isinstance(candle_raw, dict):
                return
            candle = CandleClosed.model_validate(candle_raw)
            await self._callbacks.on_closed(str(message.series_id), candle)
            return
        if event_type == "candles_batch":
            candles_raw = message.payload.get("candles")
            if not isinstance(candles_raw, list):
                return
            candles: list[CandleClosed] = []
            for item in candles_raw:
                if not isinstance(item, dict):
                    continue
                candles.append(CandleClosed.model_validate(item))
            await self._callbacks.on_batch(str(message.series_id), candles)
            return
        if event_type == "candle_forming":
            candle_raw = message.payload.get("candle")
            if not isinstance(candle_raw, dict):
                return
            candle = CandleClosed.model_validate(candle_raw)
            await self._callbacks.on_forming(str(message.series_id), candle)
            return
        if event_type == "system":
            data_payload = message.payload.get("data")
            await self._callbacks.on_system(
                str(message.series_id),
                str(message.payload.get("event") or ""),
                str(message.payload.get("message") or ""),
                dict(data_payload) if isinstance(data_payload, dict) else {},
            )
