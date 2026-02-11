from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Protocol

from .blocking import run_blocking
from .ledger_sync_service import LedgerSyncService
from .timeframe import series_id_timeframe, timeframe_to_seconds


class _StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...


class _AlignedStoreLike(_StoreLike, Protocol):
    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class _BackfillLike(Protocol):
    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int: ...


class _IngestPipelineLike(Protocol):
    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]): ...


class _RuntimeFlagsLike(Protocol):
    @property
    def enable_ledger_sync_service(self) -> bool: ...


class _LedgerRefreshOutcomeLike(Protocol):
    @property
    def refreshed(self) -> bool: ...


class _LedgerSyncLike(Protocol):
    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> _LedgerRefreshOutcomeLike: ...


class _DebugHubLike(Protocol):
    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None: ...


class _RuntimeLike(Protocol):
    @property
    def store(self) -> _AlignedStoreLike: ...

    @property
    def factor_orchestrator(self) -> _StoreLike: ...

    @property
    def overlay_orchestrator(self) -> _StoreLike: ...

    @property
    def read_ctx(self) -> _RuntimeReadCtxLike: ...

    @property
    def ingest_ctx(self) -> _RuntimeIngestCtxLike: ...

    @property
    def runtime_flags(self) -> _RuntimeFlagsLike: ...

    @property
    def debug_hub(self) -> _DebugHubLike: ...


class _RuntimeReadCtxLike(Protocol):
    @property
    def backfill(self) -> _BackfillLike: ...

    @property
    def whitelist(self) -> object: ...


class _RuntimeIngestCtxLike(Protocol):
    @property
    def ingest_pipeline(self) -> _IngestPipelineLike | None: ...


def _runtime_backfill(runtime: _RuntimeLike) -> _BackfillLike:
    return runtime.read_ctx.backfill


def _runtime_ingest_pipeline(runtime: _RuntimeLike) -> _IngestPipelineLike | None:
    return runtime.ingest_ctx.ingest_pipeline


def _runtime_ledger_sync(runtime: _RuntimeLike) -> _LedgerSyncLike | None:
    if not bool(runtime.runtime_flags.enable_ledger_sync_service):
        return None
    ingest_pipeline = _runtime_ingest_pipeline(runtime)
    if ingest_pipeline is None:
        return None
    return LedgerSyncService(
        store=runtime.store,
        factor_store=runtime.factor_orchestrator,
        overlay_store=runtime.overlay_orchestrator,
        ingest_pipeline=ingest_pipeline,
    )


@dataclass(frozen=True)
class StartupKlineSyncSeriesResult:
    series_id: str
    target_time: int | None
    before_head_time: int | None
    after_head_time: int | None
    covered_candles: int
    refreshed: bool
    error: str | None = None


@dataclass(frozen=True)
class StartupKlineSyncResult:
    enabled: bool
    target_candles: int
    series_total: int
    series_synced: int
    series_lagging: int
    series_errors: int
    duration_ms: int
    series_results: tuple[StartupKlineSyncSeriesResult, ...]


def _expected_latest_closed_time(*, now_time: int, timeframe_seconds: int) -> int:
    tf_s = max(1, int(timeframe_seconds))
    aligned = (int(now_time) // int(tf_s)) * int(tf_s)
    if aligned <= 0:
        return 0
    if aligned >= int(tf_s):
        return int(aligned - int(tf_s))
    return 0


def _target_time_for_series(*, series_id: str, now_time: int) -> int | None:
    try:
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    except Exception:
        return None
    if int(tf_s) <= 0:
        return None
    return _expected_latest_closed_time(now_time=int(now_time), timeframe_seconds=int(tf_s))


def _sync_one_series(
    *,
    store: _StoreLike,
    backfill: _BackfillLike,
    ingest_pipeline: _IngestPipelineLike | None,
    ledger_sync: _LedgerSyncLike | None,
    enable_ledger_sync_service: bool,
    series_id: str,
    target_candles: int,
    now_time: int,
) -> StartupKlineSyncSeriesResult:
    before_head_time = store.head_time(series_id)
    target_time = _target_time_for_series(series_id=series_id, now_time=int(now_time))
    if target_time is None:
        return StartupKlineSyncSeriesResult(
            series_id=str(series_id),
            target_time=None,
            before_head_time=before_head_time,
            after_head_time=before_head_time,
            covered_candles=0,
            refreshed=False,
            error="invalid_series_timeframe",
        )
    if int(target_time) <= 0:
        return StartupKlineSyncSeriesResult(
            series_id=str(series_id),
            target_time=int(target_time),
            before_head_time=before_head_time,
            after_head_time=before_head_time,
            covered_candles=0,
            refreshed=False,
            error=None,
        )

    covered_candles = int(
        backfill.ensure_tail_coverage(
            series_id=str(series_id),
            target_candles=int(target_candles),
            to_time=int(target_time),
        )
    )

    refreshed = False
    if bool(enable_ledger_sync_service) and ledger_sync is not None:
        refresh_outcome = ledger_sync.refresh_if_needed(
            series_id=str(series_id),
            up_to_time=int(target_time),
        )
        refreshed = bool(refresh_outcome.refreshed)
    elif ingest_pipeline is not None:
        ingest_pipeline.refresh_series_sync(up_to_times={str(series_id): int(target_time)})
        refreshed = True

    after_head_time = store.head_time(series_id)
    return StartupKlineSyncSeriesResult(
        series_id=str(series_id),
        target_time=int(target_time),
        before_head_time=before_head_time,
        after_head_time=after_head_time,
        covered_candles=int(covered_candles),
        refreshed=bool(refreshed),
        error=None,
    )


def _safe_series_ids(series_ids: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in series_ids or ():
        sid = str(raw or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    out.sort()
    return tuple(out)


def _is_lagging(item: StartupKlineSyncSeriesResult) -> bool:
    if item.error is not None:
        return False
    if item.target_time is None:
        return False
    if int(item.target_time) <= 0:
        return False
    if item.after_head_time is None:
        return True
    return int(item.after_head_time) < int(item.target_time)


async def run_startup_kline_sync(
    *,
    store: _StoreLike,
    backfill: _BackfillLike,
    ingest_pipeline: _IngestPipelineLike | None,
    series_ids: tuple[str, ...] | list[str] | None,
    enabled: bool,
    target_candles: int,
    ledger_sync: _LedgerSyncLike | None = None,
    enable_ledger_sync_service: bool = False,
    debug_hub: _DebugHubLike | None = None,
    now_time: int | None = None,
) -> StartupKlineSyncResult:
    normalized_series_ids = _safe_series_ids(series_ids)
    effective_target_candles = max(100, int(target_candles))
    if not bool(enabled):
        return StartupKlineSyncResult(
            enabled=False,
            target_candles=int(effective_target_candles),
            series_total=int(len(normalized_series_ids)),
            series_synced=0,
            series_lagging=0,
            series_errors=0,
            duration_ms=0,
            series_results=tuple(),
        )

    t0 = time.perf_counter()
    fixed_now_time = int(now_time) if now_time is not None else int(time.time())
    out: list[StartupKlineSyncSeriesResult] = []
    for series_id in normalized_series_ids:
        try:
            item = await run_blocking(
                _sync_one_series,
                store=store,
                backfill=backfill,
                ingest_pipeline=ingest_pipeline,
                ledger_sync=ledger_sync,
                enable_ledger_sync_service=bool(enable_ledger_sync_service),
                series_id=str(series_id),
                target_candles=int(effective_target_candles),
                now_time=int(fixed_now_time),
            )
        except Exception as exc:
            item = StartupKlineSyncSeriesResult(
                series_id=str(series_id),
                target_time=None,
                before_head_time=store.head_time(series_id),
                after_head_time=store.head_time(series_id),
                covered_candles=0,
                refreshed=False,
                error=str(exc),
            )
        out.append(item)
        if debug_hub is not None:
            debug_hub.emit(
                pipe="write",
                event="write.startup.kline_sync.series_done",
                series_id=str(series_id),
                message="startup kline sync series done",
                level="error" if item.error is not None else "info",
                data={
                    "series_id": str(series_id),
                    "target_time": item.target_time,
                    "before_head_time": item.before_head_time,
                    "after_head_time": item.after_head_time,
                    "covered_candles": int(item.covered_candles),
                    "refreshed": bool(item.refreshed),
                    "lagging": bool(_is_lagging(item)),
                    "error": item.error,
                },
            )

    series_errors = sum(1 for item in out if item.error is not None)
    series_lagging = sum(1 for item in out if _is_lagging(item))
    series_synced = sum(1 for item in out if item.error is None and not _is_lagging(item))
    result = StartupKlineSyncResult(
        enabled=True,
        target_candles=int(effective_target_candles),
        series_total=int(len(normalized_series_ids)),
        series_synced=int(series_synced),
        series_lagging=int(series_lagging),
        series_errors=int(series_errors),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        series_results=tuple(out),
    )
    if debug_hub is not None:
        debug_hub.emit(
            pipe="write",
            event="write.startup.kline_sync.done",
            message="startup kline sync done",
            data={
                "series_total": int(result.series_total),
                "series_synced": int(result.series_synced),
                "series_lagging": int(result.series_lagging),
                "series_errors": int(result.series_errors),
                "target_candles": int(result.target_candles),
                "duration_ms": int(result.duration_ms),
            },
        )
    return result


def _runtime_whitelist_series_ids(runtime: _RuntimeLike) -> tuple[str, ...]:
    raw = getattr(runtime.read_ctx.whitelist, "series_ids", ())
    if not isinstance(raw, tuple):
        try:
            raw = tuple(raw)
        except Exception:
            raw = tuple()
    return _safe_series_ids(raw)


async def run_startup_kline_sync_for_runtime(
    *,
    runtime: _RuntimeLike,
    enabled: bool,
    target_candles: int,
) -> StartupKlineSyncResult:
    ledger_sync = _runtime_ledger_sync(runtime)
    return await run_startup_kline_sync(
        store=runtime.store,
        backfill=_runtime_backfill(runtime),
        ingest_pipeline=_runtime_ingest_pipeline(runtime),
        ledger_sync=ledger_sync,
        enable_ledger_sync_service=bool(runtime.runtime_flags.enable_ledger_sync_service),
        series_ids=_runtime_whitelist_series_ids(runtime),
        enabled=bool(enabled),
        target_candles=int(target_candles),
        debug_hub=runtime.debug_hub,
    )
