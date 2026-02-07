from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .factor_orchestrator import FactorOrchestrator
from .factor_store import FactorStore
from .schemas import CandleClosed
from .store import CandleStore


def _to_unix_seconds(value: Any) -> int:
    if hasattr(value, "timestamp"):
        return int(value.timestamp())
    try:
        import pandas as pd  # type: ignore

        return int(pd.Timestamp(value).timestamp())
    except Exception:
        pass
    return int(value)


def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    raw = (os.environ.get("TRADE_CANVAS_DB_PATH") or "backend/data/market.db").strip()
    base = Path(raw)
    if base.is_absolute():
        return base
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / base).resolve()


def build_series_id(
    pair: str,
    timeframe: str,
    *,
    exchange: str | None = None,
    market: str | None = None,
) -> str:
    ex = (exchange or os.environ.get("TRADE_CANVAS_SERIES_EXCHANGE") or "binance").strip()
    mk = (market or os.environ.get("TRADE_CANVAS_SERIES_MARKET") or "futures").strip()
    return f"{ex}:{mk}:{pair}:{timeframe}"


@dataclass(frozen=True)
class LedgerAnnotateResult:
    ok: bool
    reason: str | None
    dataframe: Any


def annotate_factor_ledger(
    dataframe: Any,
    *,
    series_id: str,
    timeframe: str,
    db_path: Path | None = None,
) -> LedgerAnnotateResult:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:
        return LedgerAnnotateResult(ok=False, reason=f"pandas_missing:{exc}", dataframe=dataframe)

    df = dataframe.copy()
    if df.empty:
        df["tc_ok"] = 1
        df["tc_pen_confirmed"] = pd.Series(dtype="int64")
        df["tc_pen_dir"] = pd.Series(dtype="int64")
        df["tc_enter_long"] = pd.Series(dtype="int64")
        df["tc_enter_short"] = pd.Series(dtype="int64")
        return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)

    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(set(df.columns))
    if missing:
        return LedgerAnnotateResult(ok=False, reason=f"missing_columns:{sorted(missing)}", dataframe=dataframe)

    db = _resolve_db_path(db_path)
    store = CandleStore(db_path=db)
    factor_store = FactorStore(db_path=db)
    orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)

    df["tc_ok"] = 1
    df["tc_pen_confirmed"] = 0
    df["tc_pen_dir"] = pd.NA
    df["tc_enter_long"] = 0
    df["tc_enter_short"] = 0

    times = df["date"].map(_to_unix_seconds)
    order = times.sort_values().index
    times_by_idx = {idx: int(times.loc[idx]) for idx in order}

    store_head = store.head_time(series_id)
    to_write: list[CandleClosed] = []
    last_time: int | None = None

    for idx in order:
        open_time = times_by_idx[idx]
        if store_head is not None and open_time <= int(store_head):
            continue
        if last_time is not None and open_time == last_time:
            to_write[-1] = CandleClosed(
                candle_time=open_time,
                open=float(df.at[idx, "open"]),
                high=float(df.at[idx, "high"]),
                low=float(df.at[idx, "low"]),
                close=float(df.at[idx, "close"]),
                volume=float(df.at[idx, "volume"]),
            )
            continue
        to_write.append(
            CandleClosed(
                candle_time=open_time,
                open=float(df.at[idx, "open"]),
                high=float(df.at[idx, "high"]),
                low=float(df.at[idx, "low"]),
                close=float(df.at[idx, "close"]),
                volume=float(df.at[idx, "volume"]),
            )
        )
        last_time = open_time

    if to_write:
        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, series_id, to_write)
            conn.commit()
        orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(to_write[-1].candle_time))

    candle_head = store.head_time(series_id)
    factor_head = factor_store.head_time(series_id)
    if candle_head is not None and (factor_head is None or int(factor_head) < int(candle_head)):
        df["tc_ok"] = 0
        return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)

    if candle_head is None:
        return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)

    start_time = int(times.min())
    end_time = int(times.max())
    pen_events = factor_store.get_events_between_times(
        series_id=series_id,
        factor_name="pen",
        start_candle_time=start_time,
        end_candle_time=end_time,
    )

    pen_by_time: dict[int, list[int]] = {}
    for e in pen_events:
        if e.kind != "pen.confirmed":
            continue
        try:
            direction = int(e.payload.get("direction"))
        except Exception:
            continue
        pen_by_time.setdefault(int(e.candle_time), []).append(direction)

    for idx in order:
        t = times_by_idx[idx]
        dirs = pen_by_time.get(int(t))
        if not dirs:
            continue
        direction = int(dirs[-1])
        df.at[idx, "tc_pen_confirmed"] = 1
        df.at[idx, "tc_pen_dir"] = direction
        if direction == 1:
            df.at[idx, "tc_enter_long"] = 1
        elif direction == -1:
            df.at[idx, "tc_enter_short"] = 1

    return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)
