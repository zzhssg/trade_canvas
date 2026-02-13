from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.request import Request, urlopen

from ..core.flags import resolve_env_int, resolve_env_str


@dataclass(frozen=True)
class TopMarket:
    exchange: Literal["binance"]
    market: Literal["spot", "futures"]
    symbol: str  # e.g. "BTC/USDT"
    symbol_id: str  # e.g. "BTCUSDT"
    base_asset: str
    quote_asset: str
    last_price: float | None
    quote_volume: float | None
    price_change_percent: float | None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f else None
    if isinstance(value, str):
        try:
            f = float(value)
        except ValueError:
            return None
        return f if f == f else None
    return None


def _fetch_json(url: str, *, timeout_s: float = 5.0) -> Any:
    req = Request(url, headers={"User-Agent": "trade_canvas/0.1"})
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _spot_base_url() -> str:
    return resolve_env_str(
        "TRADE_CANVAS_BINANCE_SPOT_BASE_URL",
        fallback="https://api.binance.com",
    ).rstrip("/")


def _futures_base_url() -> str:
    return resolve_env_str(
        "TRADE_CANVAS_BINANCE_FUTURES_BASE_URL",
        fallback="https://fapi.binance.com",
    ).rstrip("/")


def _exchangeinfo_ttl_s() -> int:
    return resolve_env_int(
        "TRADE_CANVAS_BINANCE_EXCHANGEINFO_TTL_S",
        fallback=3600,
        minimum=1,
    )


def _ticker_ttl_s() -> int:
    return resolve_env_int(
        "TRADE_CANVAS_BINANCE_TICKER_TTL_S",
        fallback=10,
        minimum=1,
    )


class BinanceMarketListService:
    def __init__(self) -> None:
        self._spot_base = _spot_base_url()
        self._futures_base = _futures_base_url()
        self._exchangeinfo_ttl_s = _exchangeinfo_ttl_s()
        self._ticker_ttl_s = _ticker_ttl_s()
        self._lock = threading.Lock()
        self._exchange_info_cache: dict[str, tuple[float, dict[str, tuple[str, str]]]] = {}
        self._ticker_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def get_top_markets(
        self,
        *,
        market: Literal["spot", "futures"],
        quote_asset: str,
        limit: int,
        force_refresh: bool = False,
    ) -> tuple[list[TopMarket], bool]:
        quote_asset = quote_asset.upper().strip()
        if not quote_asset:
            quote_asset = "USDT"

        meta, meta_cached = self._get_symbol_meta(market=market, force_refresh=force_refresh)
        tickers, tickers_cached = self._get_24h_tickers(market=market, force_refresh=force_refresh)

        items: list[TopMarket] = []
        for t in tickers:
            symbol_id = str(t.get("symbol") or "").strip()
            if not symbol_id:
                continue
            m = meta.get(symbol_id)
            if not m:
                continue
            base_asset, q = m
            if q != quote_asset:
                continue

            quote_volume = _as_float(t.get("quoteVolume"))
            if quote_volume is None:
                continue

            items.append(
                TopMarket(
                    exchange="binance",
                    market=market,
                    symbol=f"{base_asset}/{q}",
                    symbol_id=symbol_id,
                    base_asset=base_asset,
                    quote_asset=q,
                    last_price=_as_float(t.get("lastPrice")),
                    quote_volume=quote_volume,
                    price_change_percent=_as_float(t.get("priceChangePercent")),
                )
            )

        items.sort(key=lambda x: float(x.quote_volume or 0.0), reverse=True)
        return items[: max(1, int(limit))], (meta_cached and tickers_cached and not force_refresh)

    def _get_symbol_meta(
        self, *, market: Literal["spot", "futures"], force_refresh: bool
    ) -> tuple[dict[str, tuple[str, str]], bool]:
        now = time.time()
        with self._lock:
            cached = self._exchange_info_cache.get(market)
            if cached and not force_refresh:
                at, meta = cached
                if now - at < self._exchangeinfo_ttl_s:
                    return meta, True

        try:
            if market == "spot":
                url = f"{self._spot_base}/api/v3/exchangeInfo"
                data = _fetch_json(url)
                meta = self._parse_spot_exchange_info(data)
            else:
                url = f"{self._futures_base}/fapi/v1/exchangeInfo"
                data = _fetch_json(url)
                meta = self._parse_futures_exchange_info(data)
        except Exception:
            with self._lock:
                cached = self._exchange_info_cache.get(market)
                if cached:
                    return cached[1], True
            raise

        with self._lock:
            self._exchange_info_cache[market] = (now, meta)
        return meta, False

    def _get_24h_tickers(
        self, *, market: Literal["spot", "futures"], force_refresh: bool
    ) -> tuple[list[dict[str, Any]], bool]:
        now = time.time()
        with self._lock:
            cached = self._ticker_cache.get(market)
            if cached and not force_refresh:
                at, tickers = cached
                if now - at < self._ticker_ttl_s:
                    return tickers, True

        try:
            if market == "spot":
                url = f"{self._spot_base}/api/v3/ticker/24hr"
            else:
                url = f"{self._futures_base}/fapi/v1/ticker/24hr"
            data = _fetch_json(url)
            tickers = list(data or [])
        except Exception:
            with self._lock:
                cached = self._ticker_cache.get(market)
                if cached:
                    return cached[1], True
            raise

        with self._lock:
            self._ticker_cache[market] = (now, tickers)
        return tickers, False

    @staticmethod
    def _parse_spot_exchange_info(data: Any) -> dict[str, tuple[str, str]]:
        meta: dict[str, tuple[str, str]] = {}
        for s in (data or {}).get("symbols", []) or []:
            if (s or {}).get("status") != "TRADING":
                continue
            symbol_id = str((s or {}).get("symbol") or "").strip()
            base = str((s or {}).get("baseAsset") or "").strip()
            quote = str((s or {}).get("quoteAsset") or "").strip()
            if not symbol_id or not base or not quote:
                continue
            meta[symbol_id] = (base, quote)
        return meta

    @staticmethod
    def _parse_futures_exchange_info(data: Any) -> dict[str, tuple[str, str]]:
        meta: dict[str, tuple[str, str]] = {}
        for s in (data or {}).get("symbols", []) or []:
            if (s or {}).get("status") != "TRADING":
                continue
            contract_type = str((s or {}).get("contractType") or "").strip()
            if contract_type and contract_type != "PERPETUAL":
                continue
            symbol_id = str((s or {}).get("symbol") or "").strip()
            base = str((s or {}).get("baseAsset") or "").strip()
            quote = str((s or {}).get("quoteAsset") or "").strip()
            if not symbol_id or not base or not quote:
                continue
            meta[symbol_id] = (base, quote)
        return meta


class MinIntervalLimiter:
    def __init__(self, *, min_interval_s: float) -> None:
        self._min_interval_s = float(min_interval_s)
        self._lock = threading.Lock()
        self._last_at: dict[str, float] = {}

    def allow(self, *, key: str) -> bool:
        now = time.time()
        with self._lock:
            last = self._last_at.get(key)
            if last is not None and (now - last) < self._min_interval_s:
                return False
            self._last_at[key] = now
            return True
