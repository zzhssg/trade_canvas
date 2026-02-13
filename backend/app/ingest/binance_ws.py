from __future__ import annotations

import asyncio
import json
import time
from typing import SupportsFloat, SupportsInt, cast

from .loop_guardrail import IngestLoopGuardrail
from ..pipelines import IngestPipeline, IngestPipelineResult
from ..schemas import CandleClosed
from ..series_id import SeriesId, parse_series_id
from ..store import CandleStore
from .ws_hotpath import flush_ws_buffer, publish_forming_with_derived, should_emit_forming
from ..ws.hub import CandleHub
from .settings import WhitelistIngestSettings
from ..derived_timeframes import DerivedTimeframeFanout


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, str, bytes, bytearray)):
            return int(value)
        return int(cast(SupportsInt, value))
    except Exception:
        return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float, str, bytes, bytearray)):
            return float(value)
        return float(cast(SupportsFloat, value))
    except Exception:
        return None


def _binance_stream_symbol(symbol: str) -> str | None:
    if not isinstance(symbol, str) or not symbol:
        return None
    base = symbol.split(":", 1)[0]
    if "/" not in base:
        return None
    return base.replace("/", "").replace("-", "").strip().lower()


def build_binance_kline_ws_url(series: SeriesId) -> str:
    if series.exchange != "binance":
        raise ValueError(f"unsupported exchange: {series.exchange!r}")
    stream_symbol = _binance_stream_symbol(series.symbol)
    if not stream_symbol:
        raise ValueError("unsupported symbol format for binance kline ws")

    tf = (series.timeframe or "").strip().lower()
    if not tf:
        raise ValueError("missing timeframe")

    if series.market == "futures":
        return f"wss://fstream.binance.com/ws/{stream_symbol}@kline_{tf}"
    if series.market == "spot":
        return f"wss://stream.binance.com:9443/ws/{stream_symbol}@kline_{tf}"
    raise ValueError(f"unsupported market: {series.market!r}")


def parse_binance_kline_payload(payload: object) -> CandleClosed | None:
    parsed = parse_binance_kline_payload_any(payload)
    if parsed is None:
        return None
    candle, is_final = parsed
    return candle if is_final else None


def parse_binance_kline_payload_any(payload: object) -> tuple[CandleClosed, bool] | None:
    if not isinstance(payload, dict):
        return None

    k = payload.get("k")
    if not isinstance(k, dict):
        return None

    open_ms_int = _coerce_int(k.get("t"))
    if open_ms_int is None:
        return None
    if open_ms_int <= 0:
        return None
    candle_time = int(open_ms_int // 1000)

    is_final = bool(k.get("x"))

    o = _coerce_float(k.get("o"))
    h = _coerce_float(k.get("h"))
    l = _coerce_float(k.get("l"))
    c = _coerce_float(k.get("c"))
    v = _coerce_float(k.get("v"))
    if o is None or h is None or l is None or c is None or v is None:
        return None

    return CandleClosed(
        candle_time=candle_time,
        open=float(o),
        high=float(h),
        low=float(l),
        close=float(c),
        volume=float(v),
    ), is_final


async def run_binance_ws_ingest_loop(
    *,
    series_id: str,
    store: CandleStore,
    hub: CandleHub,
    ingest_pipeline: IngestPipeline | None = None,
    settings: WhitelistIngestSettings,
    stop: asyncio.Event,
    market_history_source: str = "",
    derived_enabled: bool = False,
    derived_base_timeframe: str = "1m",
    derived_timeframes: tuple[str, ...] = (),
    batch_max: int = 200,
    flush_s: float = 0.5,
    forming_min_interval_ms: int = 250,
    loop_guardrail: IngestLoopGuardrail | None = None,
) -> None:
    series = parse_series_id(series_id)

    if series.exchange != "binance":
        # Supervisor should not select WS for non-binance, but be defensive.
        raise ValueError(f"unsupported exchange: {series.exchange!r}")
    if ingest_pipeline is None:
        raise RuntimeError("ingest_pipeline_not_configured")

    history_source = str(market_history_source).strip().lower()
    if store.head_time(series_id) is None and history_source == "freqtrade":
        try:
            from ..history_bootstrapper import maybe_bootstrap_from_freqtrade

            limit = int(getattr(settings, "bootstrap_backfill_count", 2000) or 2000)
            maybe_bootstrap_from_freqtrade(
                store,
                series_id=series_id,
                limit=limit,
                market_history_source=history_source,
            )
        except Exception:
            pass

    url = build_binance_kline_ws_url(series)

    batch_max = max(1, int(batch_max))
    flush_s = max(0.05, float(flush_s))

    last_emitted_time = store.head_time(series_id) or 0
    buf: list[CandleClosed] = []
    last_flush_at = time.time()

    forming_min_interval_ms = max(0, int(forming_min_interval_ms))
    forming_min_interval_s = forming_min_interval_ms / 1000.0
    last_forming_emit_at = 0.0
    last_forming_candle_time: int | None = None

    use_derived = bool(derived_enabled)
    base_timeframe = str(derived_base_timeframe).strip() or "1m"
    derived_targets = tuple(str(tf).strip() for tf in (derived_timeframes or ()) if str(tf).strip())

    fanout: DerivedTimeframeFanout | None = None
    if use_derived:
        try:
            if str(series.timeframe).strip() == str(base_timeframe).strip():
                fanout = DerivedTimeframeFanout(
                    base_timeframe=base_timeframe,
                    derived=derived_targets,
                    forming_min_interval_ms=int(forming_min_interval_ms),
                )
        except Exception:
            fanout = None

    while not stop.is_set():
        if loop_guardrail is not None:
            wait_s = float(loop_guardrail.before_attempt())
            if wait_s > 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=float(wait_s))
                except asyncio.TimeoutError:
                    pass
                continue
        try:
            import websockets

            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=2,
                max_queue=32,
            ) as upstream:
                if loop_guardrail is not None:
                    loop_guardrail.on_success()
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(upstream.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if buf and (time.time() - last_flush_at) >= flush_s:
                            last_emitted_time, last_flush_at = await flush_ws_buffer(
                                series_id=series_id,
                                ingest_pipeline=ingest_pipeline,
                                fanout=fanout,
                                buf=buf,
                                reason="timeout",
                                last_emitted_time=int(last_emitted_time),
                                last_flush_at=float(last_flush_at),
                                publish_pipeline_result=_publish_pipeline_result_from_ws,
                            )
                        continue

                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue

                    parsed = parse_binance_kline_payload_any(payload)
                    if parsed is None:
                        continue
                    candle, is_final = parsed

                    if not is_final:
                        now = time.monotonic()
                        if should_emit_forming(
                            candle_time=int(candle.candle_time),
                            last_emitted_time=int(last_emitted_time),
                            last_forming_candle_time=last_forming_candle_time,
                            last_forming_emit_at=float(last_forming_emit_at),
                            now=float(now),
                            forming_min_interval_s=float(forming_min_interval_s),
                        ):
                            await publish_forming_with_derived(
                                hub=hub,
                                series_id=series_id,
                                candle=candle,
                                fanout=fanout,
                                now=float(now),
                            )
                            last_forming_emit_at = float(now)
                            last_forming_candle_time = int(candle.candle_time)
                        continue

                    buf.append(candle)
                    if len(buf) >= batch_max or (time.time() - last_flush_at) >= flush_s:
                        last_emitted_time, last_flush_at = await flush_ws_buffer(
                            series_id=series_id,
                            ingest_pipeline=ingest_pipeline,
                            fanout=fanout,
                            buf=buf,
                            reason="threshold",
                            last_emitted_time=int(last_emitted_time),
                            last_flush_at=float(last_flush_at),
                            publish_pipeline_result=_publish_pipeline_result_from_ws,
                        )
                last_emitted_time, last_flush_at = await flush_ws_buffer(
                    series_id=series_id,
                    ingest_pipeline=ingest_pipeline,
                    fanout=fanout,
                    buf=buf,
                    reason="disconnect",
                    last_emitted_time=int(last_emitted_time),
                    last_flush_at=float(last_flush_at),
                    publish_pipeline_result=_publish_pipeline_result_from_ws,
                )
                if loop_guardrail is not None:
                    loop_guardrail.on_success()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            sleep_s = 2.0
            if loop_guardrail is not None:
                sleep_s = max(0.0, float(loop_guardrail.on_failure(error=exc)))
            if sleep_s <= 0:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=float(sleep_s))
            except asyncio.TimeoutError:
                pass


async def _publish_pipeline_result_from_ws(
    *,
    ingest_pipeline: IngestPipeline,
    pipeline_result: IngestPipelineResult,
) -> None:
    await ingest_pipeline.publish_ws(
        result=pipeline_result,
    )
