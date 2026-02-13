from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from ..market_data import MarketDataOrchestrator, WsMessageParser, WsSubscriptionCoordinator
from ..ws.protocol import WS_MSG_SUBSCRIBE, WS_MSG_UNSUBSCRIBE


async def handle_market_ws(
    ws: WebSocket,
    *,
    ws_messages: WsMessageParser,
    ws_subscriptions: WsSubscriptionCoordinator,
    market_data: MarketDataOrchestrator,
    derived_initial_backfill: Callable[..., Awaitable[None]],
    ondemand_enabled: bool,
    catchup_limit: int,
) -> None:
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            try:
                msg_type = ws_messages.parse_message_type(msg)
            except ValueError as exc:
                await ws.send_json(ws_messages.bad_request(message=str(exc)))
                continue
            payload = msg if isinstance(msg, dict) else {}

            if msg_type == WS_MSG_SUBSCRIBE:
                try:
                    subscribe_cmd = ws_messages.parse_subscribe(payload)
                except ValueError as exc:
                    await ws.send_json(ws_messages.bad_request(message=str(exc)))
                    continue

                err_payload, payloads = await ws_subscriptions.handle_subscribe(
                    ws=ws,
                    series_id=subscribe_cmd.series_id,
                    since=subscribe_cmd.since,
                    supports_batch=subscribe_cmd.supports_batch,
                    ondemand_enabled=ondemand_enabled,
                    market_data=market_data,
                    derived_initial_backfill=derived_initial_backfill,
                    catchup_limit=int(catchup_limit),
                )
                if err_payload is not None:
                    await ws.send_json(err_payload)
                    continue
                for out in payloads:
                    await ws.send_json(out)
                continue

            if msg_type == WS_MSG_UNSUBSCRIBE:
                series_id = ws_messages.parse_unsubscribe_series_id(payload)
                if series_id is not None:
                    await ws_subscriptions.unsubscribe(
                        ws=ws,
                        series_id=series_id,
                        ondemand_enabled=ondemand_enabled,
                    )
                continue

            await ws.send_json(ws_messages.unknown_message_type(msg_type=msg_type))
    except WebSocketDisconnect:
        pass
    finally:
        await ws_subscriptions.cleanup_disconnect(
            ws=ws,
            ondemand_enabled=ondemand_enabled,
        )
        try:
            await ws.close(code=1001)
        except Exception:
            pass
