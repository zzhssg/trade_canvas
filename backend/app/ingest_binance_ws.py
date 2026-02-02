from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from .schemas import CandleClosed
from .series_id import SeriesId, parse_series_id
from .store import CandleStore
from .ws_hub import CandleHub
from .plot_orchestrator import PlotOrchestrator
from .factor_orchestrator import FactorOrchestrator
from .overlay_orchestrator import OverlayOrchestrator

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
    plot_orchestrator: PlotOrchestrator | None,
    factor_orchestrator: FactorOrchestrator | None,
    overlay_orchestrator: OverlayOrchestrator | None = None,
    settings: object,  # keep signature compatible with supervisor (WhitelistIngestSettings)
    stop: asyncio.Event,
) -> None:
    series = parse_series_id(series_id)

    if series.exchange != "binance":
        # Supervisor should not select WS for non-binance, but be defensive.
        raise ValueError(f"unsupported exchange: {series.exchange!r}")

    if store.head_time(series_id) is None and (os.environ.get("TRADE_CANVAS_MARKET_HISTORY_SOURCE") or "").strip().lower() == "freqtrade":
        try:
            from .history_bootstrapper import maybe_bootstrap_from_freqtrade

            limit = int(getattr(settings, "bootstrap_backfill_count", 2000) or 2000)
            maybe_bootstrap_from_freqtrade(store, series_id=series_id, limit=limit)
        except Exception:
            pass

    url = build_binance_kline_ws_url(series)

    # Keep one sqlite connection per ingestor task to avoid repeated connect/pragma overhead.
    conn = store.connect()
    try:
        batch_max_raw = (os.environ.get("TRADE_CANVAS_BINANCE_WS_BATCH_MAX") or "").strip()
        flush_s_raw = (os.environ.get("TRADE_CANVAS_BINANCE_WS_FLUSH_S") or "").strip()
        try:
            batch_max = max(1, int(batch_max_raw)) if batch_max_raw else 200
        except ValueError:
            batch_max = 200
        try:
            flush_s = max(0.05, float(flush_s_raw)) if flush_s_raw else 0.5
        except ValueError:
            flush_s = 0.5

        last_emitted_time = store.head_time(series_id) or 0
        buf: list[CandleClosed] = []
        last_flush_at = time.time()

        forming_min_interval_raw = (os.environ.get("TRADE_CANVAS_MARKET_FORMING_MIN_INTERVAL_MS") or "").strip()
        try:
            forming_min_interval_ms = max(0, int(forming_min_interval_raw)) if forming_min_interval_raw else 250
        except ValueError:
            forming_min_interval_ms = 250
        forming_min_interval_s = forming_min_interval_ms / 1000.0
        last_forming_emit_at = 0.0
        last_forming_candle_time: int | None = None

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

            t0 = time.perf_counter()
            store.upsert_many_closed_in_conn(conn, series_id, deduped)
            conn.commit()
            db_ms = int((time.perf_counter() - t0) * 1000)

            if plot_orchestrator is not None:
                try:
                    plot_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=deduped[-1].candle_time)
                except Exception:
                    pass
            if factor_orchestrator is not None:
                try:
                    factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=deduped[-1].candle_time)
                except Exception:
                    pass
            if overlay_orchestrator is not None:
                try:
                    overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=deduped[-1].candle_time)
                except Exception:
                    pass

            t1 = time.perf_counter()
            for candle in deduped:
                await hub.publish_closed(series_id=series_id, candle=candle)
            publish_ms = int((time.perf_counter() - t1) * 1000)

            last_emitted_time = max(last_emitted_time, deduped[-1].candle_time)

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
    finally:
        try:
            conn.close()
        except Exception:
            pass
