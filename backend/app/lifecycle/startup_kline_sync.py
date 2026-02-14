from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..core.ports import AlignedStorePort, BackfillPort, DebugHubPort
from ..ledger.ports import LedgerSyncPreparePort
from ..runtime.blocking import run_blocking
from ..core.timeframe import expected_latest_closed_time, series_id_timeframe, timeframe_to_seconds

if TYPE_CHECKING:
    from ..market.runtime import MarketRuntime


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


def _target_time_for_series(*, series_id: str, now_time: int) -> int | None:
    try:
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    except (ValueError, KeyError):
        return None
    if int(tf_s) <= 0:
        return None
    return expected_latest_closed_time(now_time=int(now_time), timeframe_seconds=int(tf_s))


def _series_result(
    *,
    series_id: str,
    target_time: int | None,
    before_head_time: int | None,
    after_head_time: int | None = None,
    covered_candles: int = 0,
    refreshed: bool = False,
    error: str | BaseException | None = None,
) -> StartupKlineSyncSeriesResult:
    before = None if before_head_time is None else int(before_head_time)
    after = before if after_head_time is None else int(after_head_time)
    return StartupKlineSyncSeriesResult(
        series_id=str(series_id),
        target_time=None if target_time is None else int(target_time),
        before_head_time=before,
        after_head_time=after,
        covered_candles=max(0, int(covered_candles)),
        refreshed=bool(refreshed),
        error=None if error is None else str(error),
    )


def _sync_one_series(
    *,
    store: AlignedStorePort,
    backfill: BackfillPort,
    ledger_sync: LedgerSyncPreparePort,
    series_id: str,
    target_candles: int,
    now_time: int,
) -> StartupKlineSyncSeriesResult:
    before_head_time = store.head_time(series_id)
    target_time = _target_time_for_series(series_id=series_id, now_time=int(now_time))
    if target_time is None:
        return _series_result(
            series_id=str(series_id),
            target_time=None,
            before_head_time=before_head_time,
            error="invalid_series_timeframe",
        )
    if int(target_time) <= 0:
        return _series_result(
            series_id=str(series_id),
            target_time=int(target_time),
            before_head_time=before_head_time,
            error=None,
        )

    covered_candles = int(
        backfill.ensure_tail_coverage(
            series_id=str(series_id),
            target_candles=int(target_candles),
            to_time=int(target_time),
        )
    )

    refresh_outcome = ledger_sync.refresh_if_needed(
        series_id=str(series_id),
        up_to_time=int(target_time),
    )
    refreshed = bool(refresh_outcome.refreshed)

    after_head_time = store.head_time(series_id)
    return _series_result(
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
    store: AlignedStorePort,
    backfill: BackfillPort,
    ledger_sync: LedgerSyncPreparePort,
    series_ids: tuple[str, ...] | list[str] | None,
    enabled: bool,
    target_candles: int,
    debug_hub: DebugHubPort | None = None,
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
                ledger_sync=ledger_sync,
                series_id=str(series_id),
                target_candles=int(effective_target_candles),
                now_time=int(fixed_now_time),
            )
        except Exception as exc:
            item = _series_result(
                series_id=str(series_id),
                target_time=None,
                before_head_time=store.head_time(series_id),
                error=exc,
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


def _runtime_whitelist_series_ids(runtime: MarketRuntime) -> tuple[str, ...]:
    raw = getattr(runtime.read_ctx.whitelist, "series_ids", ())
    if not isinstance(raw, tuple):
        try:
            raw = tuple(raw)
        except (TypeError, ValueError):
            raw = tuple()
    return _safe_series_ids(raw)


async def run_startup_kline_sync_for_runtime(
    *,
    runtime: MarketRuntime,
    enabled: bool,
    target_candles: int,
) -> StartupKlineSyncResult:
    return await run_startup_kline_sync(
        store=runtime.store,
        backfill=runtime.read_ctx.backfill,
        ledger_sync=runtime.ledger_sync_service,
        series_ids=_runtime_whitelist_series_ids(runtime),
        enabled=bool(enabled),
        target_candles=int(target_candles),
        debug_hub=runtime.debug_hub,
    )
