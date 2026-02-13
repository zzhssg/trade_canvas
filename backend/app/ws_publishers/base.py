from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol

WsPubsubEventType = Literal["candle_closed", "candles_batch", "candle_forming", "system"]
WsPubsubConsumer = Callable[["WsPubsubMessage"], Awaitable[None]]


@dataclass(frozen=True)
class WsPubsubMessage:
    source: str
    series_id: str
    event_type: WsPubsubEventType
    payload: dict[str, Any]
    version: int = 1

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": int(self.version),
                "source": str(self.source),
                "series_id": str(self.series_id),
                "event_type": str(self.event_type),
                "payload": dict(self.payload),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_raw(cls, raw: str | bytes) -> "WsPubsubMessage":
        if isinstance(raw, bytes):
            data = json.loads(raw.decode("utf-8"))
        else:
            data = json.loads(str(raw))
        if not isinstance(data, dict):
            raise ValueError("ws_pubsub_message_invalid")
        source = str(data.get("source") or "").strip()
        series_id = str(data.get("series_id") or "").strip()
        event_type = str(data.get("event_type") or "").strip()
        payload = data.get("payload")
        if not source:
            raise ValueError("ws_pubsub_message_missing_source")
        if not series_id:
            raise ValueError("ws_pubsub_message_missing_series_id")
        if event_type not in {"candle_closed", "candles_batch", "candle_forming", "system"}:
            raise ValueError(f"ws_pubsub_message_invalid_event_type:{event_type}")
        if not isinstance(payload, dict):
            raise ValueError("ws_pubsub_message_invalid_payload")
        return cls(
            version=int(data.get("version") or 1),
            source=source,
            series_id=series_id,
            event_type=event_type,  # type: ignore[arg-type]
            payload=dict(payload),
        )


class WsPublisher(Protocol):
    def set_consumer(self, consumer: WsPubsubConsumer) -> None: ...

    async def start(self) -> None: ...

    async def publish(self, message: WsPubsubMessage) -> None: ...

    async def close(self) -> None: ...


class NoopWsPublisher:
    def set_consumer(self, consumer: WsPubsubConsumer) -> None:
        _ = consumer

    async def start(self) -> None:
        return None

    async def publish(self, message: WsPubsubMessage) -> None:
        _ = message
        return None

    async def close(self) -> None:
        return None
