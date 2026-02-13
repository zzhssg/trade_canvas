from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from ..derived_timeframes import DerivedTimeframeFanout
from ..pipelines import IngestPipeline, IngestPipelineResult
from ..schemas import CandleClosed
from ..ws.hub import CandleHub

logger = logging.getLogger(__name__)

PublishPipelineResultFn = Callable[..., Awaitable[None]]


def dedupe_closed_batch(*, candles: list[CandleClosed], last_emitted_time: int) -> list[CandleClosed]:
    ordered = sorted(candles, key=lambda c: c.candle_time)
    deduped: list[CandleClosed] = []
    last_time: int | None = None
    for candle in ordered:
        if candle.candle_time <= int(last_emitted_time):
            continue
        if last_time is not None and candle.candle_time == last_time:
            deduped[-1] = candle
            continue
        deduped.append(candle)
        last_time = int(candle.candle_time)
    return deduped


def build_ingest_batches(
    *,
    base_series_id: str,
    base_candles: list[CandleClosed],
    fanout: DerivedTimeframeFanout | None,
) -> dict[str, list[CandleClosed]]:
    derived_batches: dict[str, list[CandleClosed]] = {}
    if fanout is not None:
        try:
            derived_batches = fanout.on_base_closed_batch(base_series_id=base_series_id, candles=base_candles)
        except Exception:
            derived_batches = {}

    all_batches: dict[str, list[CandleClosed]] = {base_series_id: base_candles}
    for derived_series_id, derived in derived_batches.items():
        if derived:
            all_batches[derived_series_id] = derived
    return all_batches


def should_emit_forming(
    *,
    candle_time: int,
    last_emitted_time: int,
    last_forming_candle_time: int | None,
    last_forming_emit_at: float,
    now: float,
    forming_min_interval_s: float,
) -> bool:
    if int(candle_time) <= int(last_emitted_time):
        return False
    if last_forming_candle_time is None:
        return True
    if int(candle_time) != int(last_forming_candle_time):
        return True
    return (float(now) - float(last_forming_emit_at)) >= float(forming_min_interval_s)


async def publish_forming_with_derived(
    *,
    hub: CandleHub,
    series_id: str,
    candle: CandleClosed,
    fanout: DerivedTimeframeFanout | None,
    now: float,
) -> None:
    await hub.publish_forming(series_id=series_id, candle=candle)
    if fanout is None:
        return
    try:
        derived_forming = fanout.on_base_forming(
            base_series_id=series_id,
            candle=candle,
            now=now,
        )
        for derived_series_id, derived_candle in derived_forming:
            await hub.publish_forming(series_id=derived_series_id, candle=derived_candle)
    except Exception:
        pass


async def flush_ws_buffer(
    *,
    series_id: str,
    ingest_pipeline: IngestPipeline,
    fanout: DerivedTimeframeFanout | None,
    buf: list[CandleClosed],
    reason: str,
    last_emitted_time: int,
    last_flush_at: float,
    publish_pipeline_result: PublishPipelineResultFn,
) -> tuple[int, float]:
    if not buf:
        return int(last_emitted_time), float(last_flush_at)

    deduped = dedupe_closed_batch(
        candles=list(buf),
        last_emitted_time=int(last_emitted_time),
    )
    buf.clear()
    flushed_at = time.time()
    if not deduped:
        return int(last_emitted_time), float(flushed_at)

    up_to_time = int(deduped[-1].candle_time)
    all_batches = build_ingest_batches(
        base_series_id=series_id,
        base_candles=deduped,
        fanout=fanout,
    )

    pipeline_result = await ingest_pipeline.run(
        batches=all_batches,
        publish=False,
    )
    db_ms = int(pipeline_result.duration_ms)

    t1 = time.perf_counter()
    await publish_pipeline_result(
        ingest_pipeline=ingest_pipeline,
        pipeline_result=pipeline_result,
    )
    publish_ms = int((time.perf_counter() - t1) * 1000)

    emitted_time = max(int(last_emitted_time), int(up_to_time))
    logger.info(
        "market_ingest_batch source=binance_ws series_id=%s rows=%d db_ms=%d publish_ms=%d head_time=%d reason=%s",
        series_id,
        len(deduped),
        db_ms,
        publish_ms,
        emitted_time,
        reason,
    )
    return int(emitted_time), float(flushed_at)
