from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from .base import WsPubsubConsumer, WsPubsubMessage

logger = logging.getLogger(__name__)


class RedisWsPublisher:
    def __init__(
        self,
        *,
        redis_url: str,
        channel: str = "trade_canvas:market_ws",
    ) -> None:
        self._redis_url = str(redis_url or "").strip()
        self._channel = str(channel or "").strip() or "trade_canvas:market_ws"
        self._consumer: WsPubsubConsumer | None = None
        self._stop = asyncio.Event()
        self._reader_task: asyncio.Task | None = None
        self._client: Any = None
        self._pubsub: Any = None
        self._redis_async: Any = None

    def set_consumer(self, consumer: WsPubsubConsumer) -> None:
        self._consumer = consumer

    def _import_redis(self) -> Any:
        if self._redis_async is not None:
            return self._redis_async
        try:
            redis_async = importlib.import_module("redis.asyncio")
        except Exception as exc:  # pragma: no cover - import error only in misconfigured env
            raise RuntimeError("redis_asyncio_not_available") from exc
        self._redis_async = redis_async
        return redis_async

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        redis_async = self._import_redis()
        self._client = redis_async.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        return self._client

    async def start(self) -> None:
        if self._reader_task is not None:
            return
        if self._consumer is None:
            raise RuntimeError("ws_pubsub_consumer_not_set")
        client = await self._ensure_client()
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._channel)
        self._pubsub = pubsub
        self._stop.clear()
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def publish(self, message: WsPubsubMessage) -> None:
        client = await self._ensure_client()
        await client.publish(self._channel, message.to_json())

    async def _reader_loop(self) -> None:
        pubsub = self._pubsub
        if pubsub is None:
            return
        while not self._stop.is_set():
            try:
                raw_msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ws_pubsub_reader_error")
                await asyncio.sleep(0.2)
                continue
            if not raw_msg:
                await asyncio.sleep(0.01)
                continue
            if str(raw_msg.get("type")) != "message":
                continue
            raw_data = raw_msg.get("data")
            if raw_data is None:
                continue
            try:
                message = WsPubsubMessage.from_raw(raw_data)
            except Exception:
                logger.warning("ws_pubsub_invalid_message")
                continue
            consumer = self._consumer
            if consumer is None:
                continue
            try:
                await consumer(message)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ws_pubsub_consumer_error")

    async def close(self) -> None:
        self._stop.set()
        task = self._reader_task
        self._reader_task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        pubsub = self._pubsub
        self._pubsub = None
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(self._channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass

        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass
