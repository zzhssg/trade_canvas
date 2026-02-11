from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import SupportsFloat, SupportsInt, cast

from .pipelines import IngestPipeline
from .schemas import CandleClosed
from .series_id import SeriesId, parse_series_id
from .store import CandleStore
from .ws_hub import CandleHub
from .ingest_settings import WhitelistIngestSettings
from .derived_timeframes import DerivedTimeframeFanout

logger = logging.getLogger(__name__)


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
    # Binance stream uses lowercase concatenated symbol, e.g. "BTC/USDT" -> "btcusdt".
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
    """
    Parse Binance kline payload and return a CandleClosed only when the kline is finalized.

    This is the stable contract used by unit tests and the "closed-candle only" pipelines.
    """
    parsed = parse_binance_kline_payload_any(payload)
    if parsed is None:
        return None
    candle, is_final = parsed
    return candle if is_final else None


def parse_binance_kline_payload_any(payload: object) -> tuple[CandleClosed, bool] | None:
    """
    Parse Binance kline payload and return (candle, is_final).

    Used by the WS ingestor to optionally broadcast forming candles.
    """
    if not isinstance(payload, dict):
        return None

    k = payload.get("k")
    if not isinstance(k, dict):
        return None

    # Binance: kline open time is milliseconds.
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
            from .history_bootstrapper import maybe_bootstrap_from_freqtrade

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

    async def flush(reason: str) -> None:
        nonlocal buf, last_flush_at, last_emitted_time
        if not buf:
            return
        buf.sort(key=lambda c: c.candle_time)

        deduped: list[CandleClosed] = []
        last_time: int | None = None
        for candle in buf:
            if candle.candle_time <= last_emitted_time:
                continue
            if last_time is not None and candle.candle_time == last_time:
                deduped[-1] = candle
            else:
                deduped.append(candle)
                last_time = candle.candle_time

        buf = []
        last_flush_at = time.time()
        if not deduped:
            return

        up_to_time = int(deduped[-1].candle_time)
        derived_batches: dict[str, list[CandleClosed]] = {}
        if fanout is not None:
            try:
                derived_batches = fanout.on_base_closed_batch(base_series_id=series_id, candles=deduped)
            except Exception:
                derived_batches = {}

        all_batches: dict[str, list[CandleClosed]] = {series_id: deduped}
        for derived_series_id, derived in derived_batches.items():
            if derived:
                all_batches[derived_series_id] = derived

        pipeline_result = await ingest_pipeline.run(
            batches=all_batches,
            publish=False,
        )
        db_ms = int(pipeline_result.duration_ms)
        rebuilt_series = list(pipeline_result.rebuilt_series)

        t1 = time.perf_counter()
        await hub.publish_closed_batch(series_id=series_id, candles=deduped)
        for derived_series_id, derived in derived_batches.items():
            try:
                await hub.publish_closed_batch(series_id=derived_series_id, candles=derived)
            except Exception:
                pass
        for sid in rebuilt_series:
            try:
                await hub.publish_system(
                    series_id=sid,
                    event="factor.rebuild",
                    message="因子口径更新，已自动完成历史重算",
                    data={"series_id": sid},
                )
            except Exception:
                pass
        publish_ms = int((time.perf_counter() - t1) * 1000)

        last_emitted_time = max(last_emitted_time, up_to_time)

        logger.info(
            "market_ingest_batch source=binance_ws series_id=%s rows=%d db_ms=%d publish_ms=%d head_time=%d reason=%s",
            series_id,
            len(deduped),
            db_ms,
            publish_ms,
            last_emitted_time,
            reason,
        )

    while not stop.is_set():
        try:
            import websockets

            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=2,
                max_queue=32,
            ) as upstream:
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(upstream.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if buf and (time.time() - last_flush_at) >= flush_s:
                            await flush("timeout")
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
                        if candle.candle_time > last_emitted_time:
                            now = time.monotonic()
                            if (
                                candle.candle_time != last_forming_candle_time
                                or (now - last_forming_emit_at) >= forming_min_interval_s
                            ):
                                await hub.publish_forming(series_id=series_id, candle=candle)
                                if fanout is not None:
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
                                last_forming_emit_at = now
                                last_forming_candle_time = candle.candle_time
                        continue

                    buf.append(candle)
                    if len(buf) >= batch_max or (time.time() - last_flush_at) >= flush_s:
                        await flush("threshold")
                await flush("disconnect")
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(2.0)
