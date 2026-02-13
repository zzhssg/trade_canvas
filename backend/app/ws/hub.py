from __future__ import annotations

from fastapi import WebSocket

from ..core.schemas import CandleClosed
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds
from ..ws_publishers import WsPublisher, WsPubsubEventType
from .hub_delivery import CandleHubDelivery, GapBackfillHandler
from .hub_subscription_store import HubSubscriptionStore, Subscription
from .protocol import WS_MSG_CANDLE_FORMING, WS_MSG_SYSTEM
from .pubsub_bridge import WsPubsubBridge, WsPubsubCallbacks


class CandleHub:
    def __init__(
        self,
        *,
        gap_backfill_handler: GapBackfillHandler | None = None,
        publisher: WsPublisher | None = None,
        instance_id: str | None = None,
    ) -> None:
        self._subscriptions = HubSubscriptionStore()
        self._delivery = CandleHubDelivery(gap_backfill_handler=gap_backfill_handler)
        self._pubsub = WsPubsubBridge(
            publisher=publisher,
            instance_id=instance_id,
            callbacks=WsPubsubCallbacks(
                on_closed=self._consume_closed,
                on_batch=self._consume_batch,
                on_forming=self._consume_forming,
                on_system=self._consume_system,
            ),
        )

    def set_gap_backfill_handler(self, handler: GapBackfillHandler | None) -> None:
        self._delivery.set_gap_backfill_handler(handler)

    async def start_pubsub(self) -> None:
        await self._pubsub.start()

    async def close_pubsub(self) -> None:
        await self._pubsub.close()

    async def _publish_external(
        self,
        *,
        series_id: str,
        event_type: WsPubsubEventType,
        payload: dict[str, object],
    ) -> None:
        await self._pubsub.publish(
            series_id=series_id,
            event_type=event_type,
            payload=payload,
        )

    async def _consume_closed(self, series_id: str, candle: CandleClosed) -> None:
        await self.publish_closed(
            series_id=series_id,
            candle=candle,
            replicate=False,
        )

    async def _consume_batch(self, series_id: str, candles: list[CandleClosed]) -> None:
        await self.publish_closed_batch(
            series_id=series_id,
            candles=candles,
            replicate=False,
        )

    async def _consume_forming(self, series_id: str, candle: CandleClosed) -> None:
        await self.publish_forming(
            series_id=series_id,
            candle=candle,
            replicate=False,
        )

    async def _consume_system(self, series_id: str, event: str, message: str, data: dict) -> None:
        await self.publish_system(
            series_id=series_id,
            event=event,
            message=message,
            data=data,
            replicate=False,
        )

    async def close_all(self, *, code: int = 1001, reason: str = "server_shutdown") -> None:
        targets = await self._subscriptions.close_all_snapshot()
        for ws in targets:
            try:
                await ws.close(code=code, reason=reason)
            except Exception:
                pass

    async def subscribe(self, ws: WebSocket, *, series_id: str, since: int | None, supports_batch: bool = False) -> None:
        timeframe = series_id_timeframe(series_id)
        subscription = Subscription(
            series_id=series_id,
            last_sent_time=since,
            timeframe_s=timeframe_to_seconds(timeframe),
            supports_batch=bool(supports_batch),
        )
        await self._subscriptions.subscribe(ws, subscription=subscription)

    async def heal_catchup_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        timeframe_s = timeframe_to_seconds(series_id_timeframe(series_id))
        return await self._delivery.heal_catchup_gap(
            series_id=series_id,
            effective_since=effective_since,
            catchup=catchup,
            timeframe_s=timeframe_s,
        )

    async def publish_closed_batch(
        self,
        *,
        series_id: str,
        candles: list[CandleClosed],
        replicate: bool = True,
    ) -> None:
        if not candles:
            return

        candles_sorted = candles[:]
        if len(candles_sorted) > 1:
            candles_sorted.sort(key=lambda c: int(c.candle_time))
        targets = await self._subscriptions.collect_targets(series_id=series_id)

        for ws, sub in targets:
            try:
                await self._delivery.publish_closed_sequence(
                    ws=ws,
                    sub=sub,
                    series_id=series_id,
                    candles_sorted=candles_sorted,
                    allow_batch_message=True,
                )
            except Exception:
                await self.remove_ws(ws)
        if bool(replicate):
            await self._publish_external(
                series_id=series_id,
                event_type="candles_batch",
                payload={"candles": [c.model_dump() for c in candles_sorted]},
            )

    async def set_last_sent(self, ws: WebSocket, *, series_id: str, candle_time: int) -> None:
        await self._subscriptions.set_last_sent(ws, series_id=series_id, candle_time=candle_time)

    async def get_last_sent(self, ws: WebSocket, *, series_id: str) -> int | None:
        return await self._subscriptions.get_last_sent(ws, series_id=series_id)

    async def unsubscribe(self, ws: WebSocket, *, series_id: str) -> None:
        await self._subscriptions.unsubscribe(ws, series_id=series_id)

    async def remove_ws(self, ws: WebSocket) -> None:
        await self.pop_ws(ws)

    async def pop_ws(self, ws: WebSocket) -> list[str]:
        """
        Remove ws from hub and return the subscribed series_ids (best-effort).

        Used to release ondemand ingest refcounts on websocket disconnect.
        """
        return await self._subscriptions.pop_ws(ws)

    async def publish_closed(
        self,
        *,
        series_id: str,
        candle: CandleClosed,
        replicate: bool = True,
    ) -> None:
        targets = await self._subscriptions.collect_targets(series_id=series_id)
        for ws, sub in targets:
            try:
                await self._delivery.publish_closed_sequence(
                    ws=ws,
                    sub=sub,
                    series_id=series_id,
                    candles_sorted=[candle],
                    allow_batch_message=False,
                )
            except Exception:
                await self.remove_ws(ws)
        if bool(replicate):
            await self._publish_external(
                series_id=series_id,
                event_type="candle_closed",
                payload={"candle": candle.model_dump()},
            )

    async def publish_forming(
        self,
        *,
        series_id: str,
        candle: CandleClosed,
        replicate: bool = True,
    ) -> None:
        targets = await self._subscriptions.collect_targets(series_id=series_id)
        for ws, sub in targets:
            try:
                if sub.last_sent_time is not None and candle.candle_time <= sub.last_sent_time:
                    continue
                await ws.send_json(
                    {
                        "type": WS_MSG_CANDLE_FORMING,
                        "series_id": series_id,
                        "candle": candle.model_dump(),
                    }
                )
            except Exception:
                await self.remove_ws(ws)
        if bool(replicate):
            await self._publish_external(
                series_id=series_id,
                event_type="candle_forming",
                payload={"candle": candle.model_dump()},
            )

    async def publish_system(
        self,
        *,
        series_id: str,
        event: str,
        message: str,
        data: dict | None = None,
        replicate: bool = True,
    ) -> None:
        targets = [ws for ws, _ in await self._subscriptions.collect_targets(series_id=series_id)]
        payload = {
            "type": WS_MSG_SYSTEM,
            "series_id": series_id,
            "event": str(event),
            "message": str(message),
            "data": dict(data or {}),
        }
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.remove_ws(ws)
        if bool(replicate):
            await self._publish_external(
                series_id=series_id,
                event_type="system",
                payload={
                    "event": str(event),
                    "message": str(message),
                    "data": dict(data or {}),
                },
            )
