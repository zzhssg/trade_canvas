from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..factor.graph import FactorGraph, FactorSpec
from ..factor.orchestrator import FactorOrchestrator
from ..factor.plugin_registry import FactorPluginRegistry
from ..factor.runtime_config import FactorSettings
from ..factor.store import FactorStore
from ..flags import load_feature_flags
from ..runtime.flags import load_runtime_flags
from ..schemas import CandleClosed
from ..store import CandleStore
from .signal_plugin_contract import FreqtradeSignalContext, FreqtradeSignalPlugin
from .signal_plugins import build_default_freqtrade_signal_plugins


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
    repo_root = Path(__file__).resolve().parents[3]
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


@dataclass(frozen=True)
class _FreqtradeSignalRuntime:
    plugins: tuple[FreqtradeSignalPlugin, ...]
    event_bucket_by_kind: dict[tuple[str, str], str]
    event_bucket_sort_keys: dict[str, tuple[str, str]]
    event_bucket_names: tuple[str, ...]


def _build_signal_runtime(signal_plugins: tuple[FreqtradeSignalPlugin, ...] | None) -> _FreqtradeSignalRuntime:
    plugins = tuple(signal_plugins or build_default_freqtrade_signal_plugins())
    registry = FactorPluginRegistry(list(plugins))
    graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
    topo_plugins = tuple(cast(FreqtradeSignalPlugin, registry.require(name)) for name in graph.topo_order)

    by_kind: dict[tuple[str, str], str] = {}
    sort_keys: dict[str, tuple[str, str]] = {}
    bucket_names: set[str] = set()
    for plugin in topo_plugins:
        for spec in plugin.bucket_specs:
            factor_name = str(spec.factor_name)
            event_kind = str(spec.event_kind)
            bucket_name = str(spec.bucket_name)
            key = (factor_name, event_kind)
            existing_bucket = by_kind.get(key)
            if existing_bucket is not None and existing_bucket != bucket_name:
                raise RuntimeError(f"signal_bucket_conflict:{factor_name}:{event_kind}")
            by_kind[key] = bucket_name
            bucket_names.add(bucket_name)
            if spec.sort_keys is not None:
                sort_pair = (str(spec.sort_keys[0]), str(spec.sort_keys[1]))
                existing_sort = sort_keys.get(bucket_name)
                if existing_sort is not None and existing_sort != sort_pair:
                    raise RuntimeError(f"signal_bucket_sort_conflict:{bucket_name}")
                sort_keys[bucket_name] = sort_pair
    return _FreqtradeSignalRuntime(
        plugins=topo_plugins,
        event_bucket_by_kind=by_kind,
        event_bucket_sort_keys=sort_keys,
        event_bucket_names=tuple(sorted(bucket_names)),
    )


def _collect_signal_event_buckets(
    *,
    rows: list[Any],
    event_bucket_by_kind: dict[tuple[str, str], str],
    event_bucket_sort_keys: dict[str, tuple[str, str]],
    event_bucket_names: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in event_bucket_names}
    for row in rows:
        bucket_name = event_bucket_by_kind.get((str(row.factor_name), str(row.kind)))
        if bucket_name is None:
            continue
        payload = dict(row.payload or {})
        if "candle_time" not in payload:
            payload["candle_time"] = int(row.candle_time or 0)
        if "visible_time" not in payload:
            payload["visible_time"] = int(row.candle_time or 0)
        buckets[bucket_name].append(payload)

    for bucket_name, sort_pair in event_bucket_sort_keys.items():
        key_a, key_b = sort_pair
        buckets[bucket_name].sort(key=lambda d: (int(d.get(key_a) or 0), int(d.get(key_b) or 0)))
    return buckets


def annotate_factor_ledger(
    dataframe: Any,
    *,
    series_id: str,
    timeframe: str,
    db_path: Path | None = None,
    signal_plugins: tuple[FreqtradeSignalPlugin, ...] | None = None,
) -> LedgerAnnotateResult:
    try:
        __import__("pandas")
    except Exception as exc:
        return LedgerAnnotateResult(ok=False, reason=f"pandas_missing:{exc}", dataframe=dataframe)

    try:
        signal_runtime = _build_signal_runtime(signal_plugins)
    except Exception as exc:
        return LedgerAnnotateResult(ok=False, reason=f"signal_plugin_invalid:{exc}", dataframe=dataframe)

    df = dataframe.copy()
    df["tc_ok"] = 1
    for plugin in signal_runtime.plugins:
        plugin.prepare_dataframe(dataframe=df)

    if df.empty:
        return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)

    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(set(df.columns))
    if missing:
        return LedgerAnnotateResult(ok=False, reason=f"missing_columns:{sorted(missing)}", dataframe=dataframe)

    db = _resolve_db_path(db_path)
    base_flags = load_feature_flags()
    runtime_flags = load_runtime_flags(base_flags=base_flags)
    store = CandleStore(db_path=db)
    factor_store = FactorStore(db_path=db)
    orchestrator = FactorOrchestrator(
        candle_store=store,
        factor_store=factor_store,
        settings=FactorSettings(
            pivot_window_major=int(runtime_flags.factor_pivot_window_major),
            pivot_window_minor=int(runtime_flags.factor_pivot_window_minor),
            lookback_candles=int(runtime_flags.factor_lookback_candles),
            state_rebuild_event_limit=int(runtime_flags.factor_state_rebuild_event_limit),
        ),
        ingest_enabled=bool(runtime_flags.enable_factor_ingest),
        fingerprint_rebuild_enabled=bool(runtime_flags.enable_factor_fingerprint_rebuild),
        factor_rebuild_keep_candles=int(runtime_flags.factor_rebuild_keep_candles),
        logic_version_override=str(runtime_flags.factor_logic_version_override or ""),
    )

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
    factor_events = factor_store.get_events_between_times(
        series_id=series_id,
        factor_name=None,
        start_candle_time=start_time,
        end_candle_time=end_time,
    )
    buckets = _collect_signal_event_buckets(
        rows=factor_events,
        event_bucket_by_kind=signal_runtime.event_bucket_by_kind,
        event_bucket_sort_keys=signal_runtime.event_bucket_sort_keys,
        event_bucket_names=signal_runtime.event_bucket_names,
    )
    signal_ctx = FreqtradeSignalContext(
        series_id=series_id,
        timeframe=str(timeframe),
        dataframe=df,
        order=list(order),
        times_by_index=times_by_idx,
        buckets=buckets,
    )
    for plugin in signal_runtime.plugins:
        plugin.apply(ctx=signal_ctx)

    return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)
