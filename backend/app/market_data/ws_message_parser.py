from __future__ import annotations

from ..ws.protocol import (
    WS_ERR_BAD_REQUEST,
    WS_ERR_MSG_INVALID_ENVELOPE,
    WS_ERR_MSG_INVALID_SINCE,
    WS_ERR_MSG_INVALID_SUPPORTS_BATCH,
    WS_ERR_MSG_MISSING_SERIES_ID,
    WS_ERR_MSG_MISSING_TYPE,
    WS_MSG_ERROR,
    ws_err_msg_unknown_type,
)
from .contracts import WsSubscribeCommand


def build_ws_error_payload(
    *,
    code: str,
    message: str,
    series_id: str | None = None,
) -> dict:
    payload = {"type": WS_MSG_ERROR, "code": code, "message": message}
    if series_id is not None:
        payload["series_id"] = series_id
    return payload


class WsMessageParser:
    @staticmethod
    def bad_request(*, message: str) -> dict:
        return build_ws_error_payload(code=WS_ERR_BAD_REQUEST, message=message)

    def parse_message_type(self, msg: object) -> str:
        if not isinstance(msg, dict):
            raise ValueError(WS_ERR_MSG_INVALID_ENVELOPE)
        msg_type = msg.get("type")
        if not isinstance(msg_type, str) or not msg_type:
            raise ValueError(WS_ERR_MSG_MISSING_TYPE)
        return msg_type

    def unknown_message_type(self, *, msg_type: str) -> dict:
        return self.bad_request(message=ws_err_msg_unknown_type(msg_type=msg_type))

    def parse_subscribe(self, msg: dict) -> WsSubscribeCommand:
        series_id = msg.get("series_id")
        if not isinstance(series_id, str) or not series_id:
            raise ValueError(WS_ERR_MSG_MISSING_SERIES_ID)

        since = msg.get("since")
        if since is not None and not isinstance(since, int):
            raise ValueError(WS_ERR_MSG_INVALID_SINCE)

        supports_batch = msg.get("supports_batch")
        if supports_batch is not None and not isinstance(supports_batch, bool):
            raise ValueError(WS_ERR_MSG_INVALID_SUPPORTS_BATCH)

        return WsSubscribeCommand(
            series_id=series_id,
            since=since,
            supports_batch=bool(supports_batch),
        )

    def parse_unsubscribe_series_id(self, msg: dict) -> str | None:
        series_id = msg.get("series_id")
        if not isinstance(series_id, str) or not series_id:
            return None
        return series_id
