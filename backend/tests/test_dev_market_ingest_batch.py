from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _set_base_env(root: Path) -> None:
    os.environ["TRADE_CANVAS_DB_PATH"] = str(root / "market.db")
    os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "whitelist.json")
    (root / "whitelist.json").write_text('{"series_ids":[]}', encoding="utf-8")


def _clear_base_env() -> None:
    for name in (
        "TRADE_CANVAS_DB_PATH",
        "TRADE_CANVAS_WHITELIST_PATH",
        "TRADE_CANVAS_ENABLE_DEV_API",
    ):
        os.environ.pop(name, None)


def test_dev_market_batch_ingest_route_is_guarded_by_dev_api_flag() -> None:
    tmpdir = tempfile.TemporaryDirectory()
    root = Path(tmpdir.name)
    _set_base_env(root)
    try:
        with TestClient(create_app()) as client:
            resp = client.post(
                "/api/dev/market/ingest/candles_closed_batch",
                json={
                    "series_id": "binance:futures:BTC/USDT:1m",
                    "candles": [
                        {"candle_time": 60, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                    ],
                },
            )
        assert resp.status_code == 404, resp.text
    finally:
        _clear_base_env()
        tmpdir.cleanup()


def test_dev_market_batch_ingest_writes_candles_and_keeps_read_path_available() -> None:
    tmpdir = tempfile.TemporaryDirectory()
    root = Path(tmpdir.name)
    _set_base_env(root)
    os.environ["TRADE_CANVAS_ENABLE_DEV_API"] = "1"
    series_id = "binance:futures:BTC/USDT:1m"
    try:
        with TestClient(create_app()) as client:
            batch = client.post(
                "/api/dev/market/ingest/candles_closed_batch",
                json={
                    "series_id": series_id,
                    "publish_ws": False,
                    "candles": [
                        {"candle_time": 60, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                        {"candle_time": 120, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
                        {"candle_time": 180, "open": 3, "high": 3, "low": 3, "close": 3, "volume": 1},
                    ],
                },
            )
            assert batch.status_code == 200, batch.text
            payload = batch.json()
            assert payload["ok"] is True
            assert payload["series_id"] == series_id
            assert payload["count"] == 3
            assert payload["first_candle_time"] == 60
            assert payload["last_candle_time"] == 180

            candles = client.get("/api/market/candles", params={"series_id": series_id, "limit": 10})
            assert candles.status_code == 200, candles.text
            assert [item["candle_time"] for item in candles.json()["candles"]] == [60, 120, 180]

            factor = client.get("/api/factor/slices", params={"series_id": series_id, "at_time": 180, "window_candles": 2000})
            assert factor.status_code == 200, factor.text
            assert factor.json()["candle_id"] == f"{series_id}:180"
    finally:
        _clear_base_env()
        tmpdir.cleanup()
