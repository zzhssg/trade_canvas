from __future__ import annotations

from backend.app.ingest_binance_ws import build_binance_kline_ws_url, parse_binance_kline_payload
from backend.app.series_id import parse_series_id


def test_build_binance_kline_ws_url_spot() -> None:
    series = parse_series_id("binance:spot:BTC/USDT:1m")
    assert build_binance_kline_ws_url(series) == "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"


def test_build_binance_kline_ws_url_futures() -> None:
    series = parse_series_id("binance:futures:BTC/USDT:USDT:1h")
    assert build_binance_kline_ws_url(series) == "wss://fstream.binance.com/ws/btcusdt@kline_1h"


def test_parse_binance_kline_payload_finalized() -> None:
    payload = {
        "k": {
            "t": 1700000000000,
            "o": "1.0",
            "h": "2.0",
            "l": "0.5",
            "c": "1.5",
            "v": "100",
            "x": True,
        }
    }
    candle = parse_binance_kline_payload(payload)
    assert candle is not None
    assert candle.candle_time == 1700000000
    assert candle.open == 1.0
    assert candle.high == 2.0
    assert candle.low == 0.5
    assert candle.close == 1.5
    assert candle.volume == 100.0


def test_parse_binance_kline_payload_ignores_non_final() -> None:
    payload = {"k": {"t": 1700000000000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1", "x": False}}
    assert parse_binance_kline_payload(payload) is None
