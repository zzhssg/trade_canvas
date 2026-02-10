from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from .flags import resolve_env_bool
from .ws_protocol import WS_MSG_SUBSCRIBE, WS_MSG_UNSUBSCRIBE


def _ondemand_enabled(*, runtime) -> bool:
    return resolve_env_bool(
        "TRADE_CANVAS_ENABLE_ONDEMAND_INGEST",
        fallback=bool(runtime.flags.enable_ondemand_ingest),
    )


async def handle_market_ws(ws: WebSocket) -> None:
    await ws.accept()
    runtime = ws.app.state.market_runtime
    ws_messages = runtime.ws_messages
    ws_subscriptions = runtime.ws_subscriptions
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
                    ondemand_enabled=_ondemand_enabled(runtime=runtime),
                    market_data=runtime.market_data,
                    derived_initial_backfill=runtime.derived_initial_backfill,
                    catchup_limit=int(runtime.ws_catchup_limit),
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
                        ondemand_enabled=_ondemand_enabled(runtime=runtime),
                    )
                continue

            await ws.send_json(ws_messages.unknown_message_type(msg_type=msg_type))
    except WebSocketDisconnect:
        pass
    finally:
        await ws_subscriptions.cleanup_disconnect(
            ws=ws,
            ondemand_enabled=_ondemand_enabled(runtime=runtime),
        )
        try:
            await ws.close(code=1001)
        except Exception:
            pass
