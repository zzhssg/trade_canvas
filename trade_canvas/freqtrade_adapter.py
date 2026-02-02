from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _to_unix_seconds(value: Any) -> int:
    # freqtrade dataframe typically provides a timezone-aware datetime in `date`.
    if hasattr(value, "timestamp"):
        return int(value.timestamp())
    # pandas Timestamp / numpy datetime64 fallbacks
    try:
        import pandas as pd  # type: ignore

        return int(pd.Timestamp(value).timestamp())
    except Exception:
        pass
    return int(value)


def default_strategy_db_path(*, strategy_name: str) -> Path:
    explicit = os.environ.get("TRADE_CANVAS_STRATEGY_DB_PATH", "").strip()
    if explicit:
        return Path(explicit)
    # Avoid accidental cross-run persistence in backtests when env var is not set.
    tmpdir = Path(tempfile.gettempdir())
    return tmpdir / f"trade_canvas_{strategy_name}_{os.getpid()}.sqlite3"


@dataclass(frozen=True)
class KernelAnnotateResult:
    ok: bool
    reason: str | None
    dataframe: Any


def annotate_sma_cross(
    dataframe: Any,
    *,
    pair: str,
    timeframe: str,
    fast: int = 5,
    slow: int = 20,
    db_path: Path | None = None,
) -> KernelAnnotateResult:
    """
    Freqtrade-friendly bridge:
    - Consumes freqtrade candle dataframe (expects columns: date/open/high/low/close/volume)
    - Replays candles into trade_canvas sqlite-backed kernel (incremental, deterministic)
    - Annotates dataframe with:
        - `tc_ok` (1/0)
        - `tc_sma_fast`, `tc_sma_slow`
        - `tc_open_long` (1/0)
    """

    # Avoid hard dependency for callers that only want to import this module.
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        return KernelAnnotateResult(ok=False, reason=f"pandas_missing:{e}", dataframe=dataframe)

    from .kernel import SmaCrossKernel
    from .store import SqliteStore
    from .types import CandleClosed

    df = dataframe.copy()
    if df.empty:
        df["tc_ok"] = 1
        df["tc_sma_fast"] = pd.Series(dtype="float64")
        df["tc_sma_slow"] = pd.Series(dtype="float64")
        df["tc_open_long"] = pd.Series(dtype="int64")
        return KernelAnnotateResult(ok=True, reason=None, dataframe=df)

    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(set(df.columns))
    if missing:
        return KernelAnnotateResult(ok=False, reason=f"missing_columns:{sorted(missing)}", dataframe=dataframe)

    db_path = db_path or default_strategy_db_path(strategy_name="sma_cross")
    store = SqliteStore(db_path)
    conn = store.connect()
    try:
        store.init_schema(conn)

        kernel = SmaCrossKernel(store, fast=fast, slow=slow)

        # Ensure all output columns exist.
        df["tc_ok"] = 1
        df["tc_sma_fast"] = pd.NA
        df["tc_sma_slow"] = pd.NA
        df["tc_open_long"] = 0

        last_time = store.get_latest_candle_time(conn, symbol=pair, timeframe=timeframe)

        # Replay in chronological order (freqtrade df is usually ascending, but don't assume).
        # Keep index order stable for assignments.
        order = df["date"].map(_to_unix_seconds).sort_values().index

        for idx in order:
            row = df.loc[idx]
            open_time = _to_unix_seconds(row["date"])
            if last_time is not None and open_time <= last_time:
                continue

            candle = CandleClosed(
                symbol=pair,
                timeframe=timeframe,
                open_time=open_time,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            store.upsert_candle(conn, candle=candle)
            res = kernel.apply_closed(conn, candle)

            features = res.ledger.get("features", {})
            df.at[idx, "tc_sma_fast"] = features.get(f"sma_{fast}")
            df.at[idx, "tc_sma_slow"] = features.get(f"sma_{slow}")

            sig = res.ledger.get("signal")
            if isinstance(sig, dict) and sig.get("type") == "OPEN_LONG":
                df.at[idx, "tc_open_long"] = 1

        return KernelAnnotateResult(ok=True, reason=None, dataframe=df)
    finally:
        conn.close()
