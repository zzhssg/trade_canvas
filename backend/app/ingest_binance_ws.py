from __future__ import annotations

import asyncio
import json
import logging
import time

from .flags import resolve_env_float, resolve_env_int, resolve_env_str
from .pipelines import IngestPipeline
from .schemas import CandleClosed
from .series_id import SeriesId, parse_series_id
from .store import CandleStore
from .ws_hub import CandleHub
from .ingest_settings import WhitelistIngestSettings
from .derived_timeframes import DerivedTimeframeFanout, derived_enabled, derived_base_timeframe, derived_timeframes

logger = logging.getLogger(__name__)


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
    open_ms = k.get("t")
    try:
        open_ms_int = int(open_ms)
    except Exception:
        return None
    if open_ms_int <= 0:
        return None
    candle_time = int(open_ms_int // 1000)

    is_final = bool(k.get("x"))

    try:
        o = float(k.get("o"))
        h = float(k.get("h"))
        l = float(k.get("l"))
        c = float(k.get("c"))
        v = float(k.get("v"))
    except Exception:
        return None

    return CandleClosed(candle_time=candle_time, open=o, high=h, low=l, close=c, volume=v), is_final


async def run_binance_ws_ingest_loop(
    *,
    series_id: str,
    store: CandleStore,
    hub: CandleHub,
    ingest_pipeline: IngestPipeline | None = None,
    settings: WhitelistIngestSettings,
    stop: asyncio.Event,
) -> None:
    series = parse_series_id(series_id)

    if series.exchange != "binance":
        # Supervisor should not select WS for non-binance, but be defensive.
        raise ValueError(f"unsupported exchange: {series.exchange!r}")
    if ingest_pipeline is None:
        raise RuntimeError("ingest_pipeline_not_configured")

    history_source = resolve_env_str("TRADE_CANVAS_MARKET_HISTORY_SOURCE", fallback="").lower()
    if store.head_time(series_id) is None and history_source == "freqtrade":
        try:
            from .history_bootstrapper import maybe_bootstrap_from_freqtrade

            limit = int(getattr(settings, "bootstrap_backfill_count", 2000) or 2000)
            maybe_bootstrap_from_freqtrade(store, series_id=series_id, limit=limit)
        except Exception:
            pass

    url = build_binance_kline_ws_url(series)

    batch_max = resolve_env_int("TRADE_CANVAS_BINANCE_WS_BATCH_MAX", fallback=200, minimum=1)
    flush_s = resolve_env_float("TRADE_CANVAS_BINANCE_WS_FLUSH_S", fallback=0.5, minimum=0.05)

    last_emitted_time = store.head_time(series_id) or 0
    buf: list[CandleClosed] = []
    last_flush_at = time.time()

    forming_min_interval_ms = resolve_env_int(
        "TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS",
        fallback=250,
        minimum=0,
    )
    forming_min_interval_s = forming_min_interval_ms / 1000.0
    last_forming_emit_at = 0.0
    last_forming_candle_time: int | None = None

    fanout: DerivedTimeframeFanout | None = None
    if derived_enabled():
        try:
            base_tf = derived_base_timeframe()
            if str(series.timeframe).strip() == str(base_tf).strip():
                fanout = DerivedTimeframeFanout(
                    base_timeframe=base_tf,
                    derived=derived_timeframes(),
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
