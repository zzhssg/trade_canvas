from __future__ import annotations

WS_MSG_SUBSCRIBE = "subscribe"
WS_MSG_UNSUBSCRIBE = "unsubscribe"
WS_MSG_CANDLE_CLOSED = "candle_closed"
WS_MSG_CANDLES_BATCH = "candles_batch"
WS_MSG_CANDLE_FORMING = "candle_forming"
WS_MSG_GAP = "gap"
WS_MSG_SYSTEM = "system"
WS_MSG_ERROR = "error"

WS_ERR_BAD_REQUEST = "bad_request"
WS_ERR_CAPACITY = "capacity"

WS_ERR_MSG_INVALID_ENVELOPE = "invalid message envelope"
WS_ERR_MSG_MISSING_TYPE = "missing message type"
WS_ERR_MSG_MISSING_SERIES_ID = "missing series_id"
WS_ERR_MSG_INVALID_SINCE = "invalid since"
WS_ERR_MSG_INVALID_SUPPORTS_BATCH = "invalid supports_batch"
WS_ERR_MSG_ONDEMAND_CAPACITY = "ondemand_ingest_capacity"


def ws_err_msg_unknown_type(*, msg_type: str) -> str:
    return f"unknown message type: {msg_type}"
