from __future__ import annotations

import json
from pathlib import Path

from .config import load_settings
from .market_flags import market_history_source
from .schemas import CandleClosed
from .series_id import SeriesId, parse_series_id
from .store import CandleStore


def _resolve_freqtrade_datadir() -> Path | None:
    settings = load_settings()
    if settings.freqtrade_datadir is not None:
        return settings.freqtrade_datadir

    cfg_path = settings.freqtrade_config_path
    if cfg_path is None or not cfg_path.exists():
        return None

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    datadir_raw = str(cfg.get("datadir") or "").strip()
    if datadir_raw:
        datadir = Path(datadir_raw).expanduser()
        if not datadir.is_absolute():
            datadir = (settings.freqtrade_root / datadir).resolve()
        return datadir

    # Heuristic fallback: common freqtrade default under userdir.
    userdir = settings.freqtrade_userdir or (settings.freqtrade_root / "user_data")
    candidate = (userdir / "data").resolve()
    return candidate if candidate.exists() else None


def _candidate_ohlcv_paths(datadir: Path, series: SeriesId) -> list[Path]:
    tf = series.timeframe
    symbol = series.symbol

    def sanitize(sym: str) -> str:
        return sym.replace("/", "_").replace(":", "_")

    def futures_symbol_candidates(sym: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        def add(candidate_symbol: str) -> None:
            sanitized = sanitize(candidate_symbol)
            if sanitized in seen:
                return
            seen.add(sanitized)
            out.append(sanitized)

        add(sym)

        base_symbol = sym.split(":", 1)[0]
        add(base_symbol)

        if "/" in base_symbol:
            base, quote = base_symbol.split("/", 1)
            settle = quote
            if ":" in sym:
                settle = sym.split(":", 1)[1] or quote
            add(f"{base}/{quote}:{settle}")

        return out

    # datadir may be either:
    # - .../user_data/data/<exchange> (trade_system style), or
    # - .../user_data/data (freqtrade default), with <exchange>/ inside.
    roots = [datadir, datadir / series.exchange]

    out: list[Path] = []
    if series.market == "futures":
        names = [f"{candidate}-{tf}-futures.feather" for candidate in futures_symbol_candidates(symbol)]
        for root in roots:
            out.extend([root / "futures" / n for n in names])
            out.extend([root / n for n in names])
    else:
        names = [f"{sanitize(symbol)}-{tf}.feather"]
        for root in roots:
            out.extend([root / n for n in names])

    # De-dup while preserving order.
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _find_freqtrade_ohlcv_file(series: SeriesId) -> Path | None:
    datadir = _resolve_freqtrade_datadir()
    if datadir is None:
        return None
    for p in _candidate_ohlcv_paths(datadir, series):
        if p.exists():
            return p
    return None


def _read_freqtrade_feather(path: Path, *, limit: int) -> list[CandleClosed]:
    import pandas as pd
    import pyarrow.feather as feather

    table = feather.read_table(path, columns=["date", "open", "high", "low", "close", "volume"])
    if table.num_rows <= 0:
        return []

    df = table.to_pandas()
    if df.empty:
        return []

    date_col = df["date"]
    if pd.api.types.is_datetime64_any_dtype(date_col):
        ts_ns = date_col.astype("int64", copy=False)
        candle_time = (ts_ns // 1_000_000_000).astype("int64", copy=False)
    elif pd.api.types.is_integer_dtype(date_col):
        ts = date_col.astype("int64", copy=False)
        # Heuristic: seconds ~ 1e9, ms ~ 1e12, ns ~ 1e18.
        max_v = int(ts.max()) if not ts.empty else 0
        if max_v > 10**14:
            candle_time = (ts // 1_000_000_000).astype("int64", copy=False)
        elif max_v > 10**11:
            candle_time = (ts // 1000).astype("int64", copy=False)
        else:
            candle_time = ts
    else:
        parsed = pd.to_datetime(date_col, utc=True, errors="coerce")
        parsed = parsed.dropna()
        if parsed.empty:
            return []
        ts_ns = parsed.astype("int64", copy=False)
        candle_time = (ts_ns // 1_000_000_000).astype("int64", copy=False)
        df = df.loc[parsed.index]

    df = df.assign(candle_time=candle_time)
    df = df.dropna(subset=["candle_time", "open", "high", "low", "close", "volume"])
    if df.empty:
        return []

    df = df.sort_values("candle_time", kind="stable")
    df = df.drop_duplicates(subset=["candle_time"], keep="last")
    if limit > 0 and len(df) > limit:
        df = df.iloc[-limit:].copy()

    out: list[CandleClosed] = []
    for row in df.itertuples(index=False):
        out.append(
            CandleClosed(
                candle_time=int(getattr(row, "candle_time")),
                open=float(getattr(row, "open")),
                high=float(getattr(row, "high")),
                low=float(getattr(row, "low")),
                close=float(getattr(row, "close")),
                volume=float(getattr(row, "volume")),
            )
        )
    return out


def maybe_bootstrap_from_freqtrade(store: CandleStore, *, series_id: str, limit: int) -> int:
    """
    Best-effort import (tail) OHLCV from freqtrade datadir into CandleStore.
    Returns the number of candles written (0 if skipped / not found).
    """
    if market_history_source() != "freqtrade":
        return 0

    try:
        series = parse_series_id(series_id)
    except Exception:
        return 0

    if store.head_time(series_id) is not None:
        return 0

    path = _find_freqtrade_ohlcv_file(series)
    if path is None:
        return 0

    candles = _read_freqtrade_feather(path, limit=max(int(limit), 1))
    if not candles:
        return 0

    with store.connect() as conn:
        store.upsert_many_closed_in_conn(conn, series_id, candles)
        conn.commit()

    return len(candles)


def backfill_tail_from_freqtrade(store: CandleStore, *, series_id: str, limit: int) -> int:
    """
    Best-effort tail backfill (append/update) from freqtrade datadir.
    Unlike maybe_bootstrap_from_freqtrade, this runs even if the store already has data.
    Returns the number of candles written (0 if skipped / not found).
    """
    if market_history_source() != "freqtrade":
        return 0

    try:
        series = parse_series_id(series_id)
    except Exception:
        return 0

    path = _find_freqtrade_ohlcv_file(series)
    if path is None:
        return 0

    candles = _read_freqtrade_feather(path, limit=max(int(limit), 1))
    if not candles:
        return 0

    with store.connect() as conn:
        store.upsert_many_closed_in_conn(conn, series_id, candles)
        conn.commit()

    return len(candles)
