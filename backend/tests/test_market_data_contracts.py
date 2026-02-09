from __future__ import annotations

from backend.app.market_data.contracts import (
    BackfillGapRequest,
    BackfillGapResult,
    CatchupReadRequest,
    CatchupReadResult,
    FreshnessSnapshot,
    WsCatchupRequest,
    WsEmitRequest,
    WsEmitResult,
)
from backend.app.schemas import CandleClosed


def test_contract_dataclasses_basic_shape() -> None:
    snap = FreshnessSnapshot(
        series_id="binance:futures:BTC/USDT:1m",
        head_time=1700000000,
        now_time=1700000030,
        lag_seconds=30,
        state="fresh",
    )
    assert snap.state == "fresh"
    assert snap.lag_seconds == 30



def test_backfill_gap_contract_records_range() -> None:
    req = BackfillGapRequest(
        series_id="binance:futures:BTC/USDT:1m",
        expected_next_time=1700000060,
        actual_time=1700000180,
    )
    res = BackfillGapResult(
        series_id=req.series_id,
        expected_next_time=req.expected_next_time,
        actual_time=req.actual_time,
        filled_count=2,
    )
    assert res.actual_time > res.expected_next_time
    assert res.filled_count == 2



def test_catchup_contract_keeps_effective_since_and_gap() -> None:
    req = CatchupReadRequest(series_id="binance:futures:BTC/USDT:1m", since=1700000000, limit=5000)
    c = CandleClosed(candle_time=1700000060, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
    out = CatchupReadResult(
        series_id=req.series_id,
        effective_since=req.since,
        candles=[c],
        gap_payload=None,
    )
    assert out.effective_since == 1700000000
    assert out.candles[0].candle_time == 1700000060


def test_ws_catchup_request_contract_shape() -> None:
    req = WsCatchupRequest(
        series_id="binance:futures:BTC/USDT:1m",
        since=1700000000,
        last_sent=1700000060,
        limit=5000,
    )
    assert req.last_sent == 1700000060
    assert req.candles is None


def test_ws_emit_contract_shape() -> None:
    req = WsEmitRequest(
        series_id="binance:futures:BTC/USDT:1m",
        supports_batch=True,
        catchup=[],
        gap_payload={"type": "gap"},
    )
    out = WsEmitResult(payloads=[{"type": "gap"}], last_sent_time=None)
    assert req.supports_batch is True
    assert out.last_sent_time is None
