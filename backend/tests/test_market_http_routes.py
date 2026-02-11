from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.dependencies import get_market_ledger_warmup_service, get_market_query_service
from backend.app.main import create_app
from backend.app.schemas import GetCandlesResponse


class _QueryStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, int]] = []

    def get_candles(self, *, series_id: str, since: int | None, limit: int) -> GetCandlesResponse:
        self.calls.append((str(series_id), None if since is None else int(since), int(limit)))
        return GetCandlesResponse(series_id=str(series_id), server_head_time=220, candles=[])


class _WarmupStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def ensure_ledgers_warm(self, *, series_id: str, store_head_time: int | None) -> None:
        self.calls.append((str(series_id), None if store_head_time is None else int(store_head_time)))


def test_market_candles_route_calls_warmup_after_query_response() -> None:
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "market.db"
    whitelist_path = Path(tmpdir.name) / "whitelist.json"
    whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
    os.environ["TRADE_CANVAS_DB_PATH"] = str(db_path)
    os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(whitelist_path)
    query_stub = _QueryStub()
    warmup_stub = _WarmupStub()
    try:
        app = create_app()
        app.dependency_overrides[get_market_query_service] = lambda: query_stub
        app.dependency_overrides[get_market_ledger_warmup_service] = lambda: warmup_stub

        with TestClient(app) as client:
            resp = client.get(
                "/api/market/candles",
                params={"series_id": "binance:futures:BTC/USDT:1m", "since": 100, "limit": 10},
            )

        assert resp.status_code == 200, resp.text
        assert query_stub.calls == [("binance:futures:BTC/USDT:1m", 100, 10)]
        assert warmup_stub.calls == [("binance:futures:BTC/USDT:1m", 220)]
    finally:
        os.environ.pop("TRADE_CANVAS_DB_PATH", None)
        os.environ.pop("TRADE_CANVAS_WHITELIST_PATH", None)
        tmpdir.cleanup()
