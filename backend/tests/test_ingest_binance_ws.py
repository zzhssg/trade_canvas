from __future__ import annotations

import asyncio

from backend.app.ingest.binance_ws import (
    _publish_pipeline_result_from_ws,
    build_binance_kline_ws_url,
    parse_binance_kline_payload,
)
from backend.app.pipelines import IngestPipelineResult, IngestSeriesBatch
from backend.app.core.schemas import CandleClosed
from backend.app.core.series_id import parse_series_id


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


def _candle(t: int, price: float = 1.0) -> CandleClosed:
    return CandleClosed(candle_time=int(t), open=price, high=price, low=price, close=price, volume=1.0)


class _PipelineSpy:
    def __init__(self) -> None:
        self.publish_ws_calls: list[int] = []

    async def publish_ws(
        self,
        *,
        result: IngestPipelineResult,
    ) -> None:
        self.publish_ws_calls.append(len(result.series_batches))


def _result_for(series_id: str) -> IngestPipelineResult:
    return IngestPipelineResult(
        series_batches=(
            IngestSeriesBatch(
                series_id=series_id,
                candles=(_candle(100),),
                up_to_candle_time=100,
            ),
        ),
        rebuilt_series=(series_id,),
        steps=(),
        duration_ms=1,
    )


def test_publish_pipeline_result_from_ws_calls_publish_ws() -> None:
    pipeline = _PipelineSpy()
    result = _result_for("binance:futures:BTC/USDT:1m")

    asyncio.run(
        _publish_pipeline_result_from_ws(
            ingest_pipeline=pipeline,  # type: ignore[arg-type]
            pipeline_result=result,
        )
    )

    assert pipeline.publish_ws_calls == [1]


def test_publish_pipeline_result_from_ws_handles_empty_batches() -> None:
    pipeline = _PipelineSpy()
    series_id = "binance:futures:BTC/USDT:1m"
    result = IngestPipelineResult(
        series_batches=(),
        rebuilt_series=(series_id,),
        steps=(),
        duration_ms=1,
    )

    asyncio.run(
        _publish_pipeline_result_from_ws(
            ingest_pipeline=pipeline,  # type: ignore[arg-type]
            pipeline_result=result,
        )
    )

    assert pipeline.publish_ws_calls == [0]
