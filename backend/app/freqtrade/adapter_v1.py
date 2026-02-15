from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..core.event_buckets import build_event_bucket_config
from ..core.service_errors import ServiceError
from ..factor.capability_manifest import FactorCapabilitySpec
from ..factor.graph import FactorGraph, FactorSpec
from ..factor.orchestrator import FactorOrchestrator
from ..factor.plugin_registry import FactorPluginRegistry
from ..factor.runtime_config import build_factor_orchestrator_runtime_config
from ..factor.store import FactorStore
from ..feature import FeatureOrchestrator, FeatureReadService, FeatureSettings, FeatureStore
from ..pipelines import IngestPipeline
from ..runtime.flags import load_runtime_flags
from ..core.schemas import CandleClosed
from ..storage.candle_store import CandleStore
from .feature_bridge import build_signal_buckets_from_features, required_feature_factors
from .signal_plugin_contract import FreqtradeSignalBucketSpec, FreqtradeSignalContext, FreqtradeSignalPlugin
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
    bucket_specs: tuple[FreqtradeSignalBucketSpec, ...]


def _build_signal_runtime(signal_plugins: tuple[FreqtradeSignalPlugin, ...] | None) -> _FreqtradeSignalRuntime:
    plugins = tuple(signal_plugins or build_default_freqtrade_signal_plugins())
    registry = FactorPluginRegistry(list(plugins))
    graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
    topo_plugins = tuple(cast(FreqtradeSignalPlugin, registry.require(name)) for name in graph.topo_order)

    bucket_specs = tuple(spec for plugin in topo_plugins for spec in plugin.bucket_specs)
    build_event_bucket_config(
        bucket_specs=bucket_specs,
        conflict_prefix="signal",
    )
    return _FreqtradeSignalRuntime(
        plugins=topo_plugins,
        bucket_specs=bucket_specs,
    )


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
    runtime_flags = load_runtime_flags()
    factor_runtime_config = build_factor_orchestrator_runtime_config(runtime_flags=runtime_flags)
    store = CandleStore(db_path=db)
    factor_store = FactorStore(db_path=db)
    feature_store = FeatureStore(db_path=db)
    orchestrator = FactorOrchestrator(
        candle_store=store,
        factor_store=factor_store,
        settings=factor_runtime_config.settings,
        ingest_enabled=factor_runtime_config.ingest_enabled,
        fingerprint_rebuild_enabled=factor_runtime_config.fingerprint_rebuild_enabled,
        factor_rebuild_keep_candles=factor_runtime_config.rebuild_keep_candles,
        logic_version_override=factor_runtime_config.logic_version_override,
    )
    required_feature_factor_names = required_feature_factors(bucket_specs=signal_runtime.bucket_specs)
    feature_required = bool(required_feature_factor_names)
    feature_orchestrator = FeatureOrchestrator(
        factor_store=factor_store,
        feature_store=feature_store,
        capability_overrides={
            factor_name: FactorCapabilitySpec(
                factor_name=factor_name,
                enable_feature=True,
            )
            for factor_name in required_feature_factor_names
        },
        settings=FeatureSettings(
            ingest_enabled=bool(runtime_flags.enable_feature_ingest),
        ),
    )
    feature_read_service = FeatureReadService(
        store=store,
        feature_store=feature_store,
        strict_mode=bool(runtime_flags.enable_feature_strict_read),
    )
    ingest_pipeline = IngestPipeline(
        store=store,
        factor_orchestrator=orchestrator,
        feature_orchestrator=feature_orchestrator if feature_required else None,
        overlay_orchestrator=None,
        hub=None,
        candle_compensate_on_error=True,
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
        try:
            ingest_pipeline.run_sync(batches={series_id: to_write})
        except Exception:
            df["tc_ok"] = 0
            return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)

    candle_head = store.head_time(series_id)
    factor_head = factor_store.head_time(series_id)
    feature_head = feature_store.head_time(series_id)
    if candle_head is not None and (factor_head is None or int(factor_head) < int(candle_head)):
        df["tc_ok"] = 0
        return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)
    if feature_required and not feature_orchestrator.enabled():
        df["tc_ok"] = 0
        return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)
    if feature_required and candle_head is not None and (feature_head is None or int(feature_head) < int(candle_head)):
        df["tc_ok"] = 0
        return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)

    if candle_head is None:
        return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)

    feature_rows_by_time: dict[int, dict[str, Any]] = {}
    if feature_required:
        try:
            feature_batch = feature_read_service.read_batch(
                series_id=series_id,
                at_time=int(times.max()),
                window_candles=max(1, int(len(order))),
                ensure_fresh=True,
                limit=max(1, int(len(order)) + 10),
            )
        except ServiceError:
            df["tc_ok"] = 0
            return LedgerAnnotateResult(ok=False, reason="ledger_out_of_sync", dataframe=df)
        for row in feature_batch.rows:
            feature_rows_by_time[int(row.candle_time)] = dict(row.values or {})

    buckets = build_signal_buckets_from_features(
        bucket_specs=signal_runtime.bucket_specs,
        feature_rows_by_time=feature_rows_by_time,
        times=[int(times_by_idx[idx]) for idx in order],
    )
    signal_ctx = FreqtradeSignalContext(
        series_id=series_id,
        timeframe=str(timeframe),
        dataframe=df,
        order=list(order),
        times_by_index=times_by_idx,
        buckets=buckets,
        feature_rows_by_time=feature_rows_by_time,
    )
    for plugin in signal_runtime.plugins:
        plugin.apply(ctx=signal_ctx)

    return LedgerAnnotateResult(ok=True, reason=None, dataframe=df)
