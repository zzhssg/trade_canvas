from __future__ import annotations

import asyncio
import logging
import os
import time
from time import perf_counter
from dataclasses import dataclass

from .blocking import run_blocking
from .schemas import CandleClosed
from .series_id import SeriesId, parse_series_id
from .store import CandleStore
from .timeframe import timeframe_to_seconds
from .ws_hub import CandleHub
from .plot_orchestrator import PlotOrchestrator
from .factor_orchestrator import FactorOrchestrator
from .overlay_orchestrator import OverlayOrchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhitelistIngestSettings:
    grace_window_s: int = 5
    poll_interval_s: float = 1.0
    batch_limit: int = 1000
    bootstrap_backfill_count: int = 2000


def _make_exchange_client(series: SeriesId):
    import ccxt  # imported lazily so tests don't require it unless ingest is enabled

    if series.exchange != "binance":
        raise ValueError(f"unsupported exchange: {series.exchange!r}")

    timeout_ms_raw = (os.environ.get("TRADE_CANVAS_CCXT_TIMEOUT_MS") or "").strip()
    timeout_ms = 10_000
    if timeout_ms_raw:
        try:
            timeout_ms = max(1000, int(timeout_ms_raw))
        except ValueError:
            timeout_ms = 10_000

    # ccxt uses `timeout` (ms) for HTTP requests; without it, a stalled request can look like
    # the backend "freezing" (threads waiting on network forever).
    options = {"enableRateLimit": True, "timeout": timeout_ms}
    if series.market == "spot":
        return ccxt.binance(options)
    if series.market == "futures":
        return ccxt.binanceusdm(options)
    raise ValueError(f"unsupported market: {series.market!r}")


def ccxt_symbol_for_series(series: SeriesId) -> str:
    """
    Map our series symbol format to the CCXT market symbol.

    - spot: "BTC/USDT"
    - futures (binanceusdm): "BTC/USDT:USDT"
    """
    if series.market != "futures":
        return series.symbol

    if ":" in series.symbol:
        return series.symbol

    if "/" not in series.symbol:
        return series.symbol

    base, quote = series.symbol.split("/", 1)
    base = base.strip()
    quote = quote.strip()
    if not base or not quote:
        return series.symbol
    return f"{base}/{quote}:{quote}"


async def _fetch_ohlcv(exchange, symbol: str, timeframe: str, since_ms: int | None, limit: int):
    return await run_blocking(exchange.fetch_ohlcv, symbol, timeframe, since_ms, limit)


async def run_whitelist_ingest_loop(
    *,
    series_id: str,
    store: CandleStore,
    hub: CandleHub,
    plot_orchestrator: PlotOrchestrator | None,
    factor_orchestrator: FactorOrchestrator | None,
    overlay_orchestrator: OverlayOrchestrator | None,
    settings: WhitelistIngestSettings,
    stop: asyncio.Event,
) -> None:
    series = parse_series_id(series_id)
    timeframe_s = timeframe_to_seconds(series.timeframe)
    exchange = _make_exchange_client(series)
    ccxt_symbol = ccxt_symbol_for_series(series)

    try:
        head = store.head_time(series_id)
        if head is None and (os.environ.get("TRADE_CANVAS_MARKET_HISTORY_SOURCE") or "").strip().lower() == "freqtrade":
            try:
                from .history_bootstrapper import maybe_bootstrap_from_freqtrade

                maybe_bootstrap_from_freqtrade(store, series_id=series_id, limit=settings.bootstrap_backfill_count)
                head = store.head_time(series_id)
            except Exception:
                head = store.head_time(series_id)
        since_ms = None if head is None else int(head * 1000)
        if head is None:
            now_s = int(time.time())
            # Try to backfill at least the default frontend tail window.
            since_ms = int((now_s - (settings.bootstrap_backfill_count + 10) * timeframe_s) * 1000)

        while not stop.is_set():
            try:
                rows = await _fetch_ohlcv(exchange, ccxt_symbol, series.timeframe, since_ms, settings.batch_limit)
                now_s = int(time.time())

                to_write: list[CandleClosed] = []
                max_open_time_s: int | None = None

                for row in rows or []:
                    open_time_s = int(row[0] // 1000)
                    max_open_time_s = open_time_s if max_open_time_s is None else max(max_open_time_s, open_time_s)

                    # Only ingest closed candles.
                    if open_time_s + timeframe_s > now_s - settings.grace_window_s:
                        continue

                    to_write.append(
                        CandleClosed(
                            candle_time=open_time_s,
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[5]),
                        )
                    )

                if to_write:
                    to_write.sort(key=lambda c: c.candle_time)

                    # CCXT since_ms semantics may include the last candle, so dedupe by candle_time.
                    deduped: list[CandleClosed] = []
                    last_time: int | None = None
                    for candle in to_write:
                        if last_time is not None and candle.candle_time == last_time:
                            deduped[-1] = candle
                        else:
                            deduped.append(candle)
                            last_time = candle.candle_time
                    to_write = deduped

                    # IMPORTANT: keep the asyncio event loop responsive.
                    # SQLite writes and factor/overlay computation are sync and may take seconds for large batches.
                    up_to_time = int(to_write[-1].candle_time)

                    def _persist_and_compute() -> int:
                        t0 = perf_counter()
                        with store.connect() as conn:
                            store.upsert_many_closed_in_conn(conn, series_id, to_write)
                            conn.commit()

                        if plot_orchestrator is not None:
                            try:
                                plot_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=up_to_time)
                            except Exception:
                                pass
                        if factor_orchestrator is not None:
                            try:
                                factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=up_to_time)
                            except Exception:
                                pass
                        if overlay_orchestrator is not None:
                            try:
                                overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=up_to_time)
                            except Exception:
                                pass
                        return int((perf_counter() - t0) * 1000)

                    db_ms = await run_blocking(_persist_and_compute)

                    t1 = time.perf_counter()
                    await hub.publish_closed_batch(series_id=series_id, candles=to_write)
                    publish_ms = int((time.perf_counter() - t1) * 1000)

                    logger.info(
                        "market_ingest_batch source=ccxt series_id=%s rows=%d db_ms=%d publish_ms=%d head_time=%d",
                        series_id,
                        len(to_write),
                        db_ms,
                        publish_ms,
                        to_write[-1].candle_time,
                    )

                    if max_open_time_s is not None:
                        since_ms = int(max_open_time_s * 1000)

                if not to_write:
                    await asyncio.sleep(settings.poll_interval_s)
            except Exception:
                await asyncio.sleep(2.0)
    finally:
        # Release network resources when a job is stopped/cancelled.
        try:
            close = getattr(exchange, "close", None)
            if callable(close):
                await run_blocking(close)
        except Exception:
            pass
