from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol

from ..market_data import CatchupReadRequest, MarketDataOrchestrator
from ..core.ports import BackfillPort, DebugHubPort
from ..runtime.metrics import RuntimeMetrics
from ..core.schemas import GetCandlesResponse

class _RuntimeFlagsLike(Protocol):
    @property
    def enable_market_auto_tail_backfill(self) -> bool: ...

    @property
    def market_auto_tail_backfill_max_candles(self) -> int | None: ...

    @property
    def enable_debug_api(self) -> bool: ...


_DebugHubLike = DebugHubPort


@dataclass(frozen=True)
class MarketQueryService:
    market_data: MarketDataOrchestrator
    backfill: BackfillPort
    runtime_flags: _RuntimeFlagsLike
    debug_hub: _DebugHubLike
    runtime_metrics: RuntimeMetrics | None = None
    backfill_cooldown_seconds: float = 2.0
    _backfill_guard_lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
    _backfill_guard_state: dict[str, tuple[bool, float]] = field(default_factory=dict, init=False, repr=False, compare=False)

    def _try_acquire_backfill_slot(self, *, series_id: str) -> bool:
        cooldown = max(0.1, float(self.backfill_cooldown_seconds))
        now = float(time.monotonic())
        with self._backfill_guard_lock:
            in_flight, last_run = self._backfill_guard_state.get(series_id, (False, 0.0))
            if bool(in_flight):
                return False
            if now - float(last_run) < cooldown:
                return False
            self._backfill_guard_state[series_id] = (True, now)
            return True

    def _release_backfill_slot(self, *, series_id: str) -> None:
        now = float(time.monotonic())
        with self._backfill_guard_lock:
            _, last_run = self._backfill_guard_state.get(series_id, (False, 0.0))
            self._backfill_guard_state[series_id] = (False, max(float(last_run), now))

    def _effective_backfill_target(self, *, limit: int) -> int:
        target = max(1, int(limit))
        max_candles = self.runtime_flags.market_auto_tail_backfill_max_candles
        if max_candles is not None:
            target = min(int(target), max(1, int(max_candles)))
        return int(target)

    def auto_tail_backfill_enabled(self) -> bool:
        return bool(self.runtime_flags.enable_market_auto_tail_backfill)

    def ensure_tail_coverage(self, *, series_id: str, limit: int) -> None:
        if not self.auto_tail_backfill_enabled():
            return
        if not self._try_acquire_backfill_slot(series_id=series_id):
            return
        try:
            self.backfill.ensure_tail_coverage(
                series_id=series_id,
                target_candles=self._effective_backfill_target(limit=int(limit)),
                to_time=None,
            )
        finally:
            self._release_backfill_slot(series_id=series_id)

    def get_candles(
        self,
        *,
        series_id: str,
        since: int | None,
        limit: int,
        ensure_coverage: bool = True,
    ) -> GetCandlesResponse:
        t0 = time.perf_counter()
        try:
            if bool(ensure_coverage):
                self.ensure_tail_coverage(series_id=series_id, limit=int(limit))
            read_result = self.market_data.read_candles(
                CatchupReadRequest(
                    series_id=series_id,
                    since=None if since is None else int(since),
                    limit=int(limit),
                )
            )
            candles = list(read_result.candles)
            head_time = self.market_data.freshness(series_id=series_id).head_time
        except Exception:
            metrics = self.runtime_metrics
            duration_ms = (time.perf_counter() - t0) * 1000.0
            if metrics is not None:
                metrics.incr(
                    "market_query_candles_requests_total",
                    labels={"result": "error"},
                )
                metrics.observe_ms(
                    "market_query_candles_duration_ms",
                    duration_ms=duration_ms,
                    labels={"result": "error"},
                )
            raise

        duration_ms = (time.perf_counter() - t0) * 1000.0
        metrics = self.runtime_metrics
        if metrics is not None:
            metrics.incr(
                "market_query_candles_requests_total",
                labels={"result": "ok"},
            )
            metrics.observe_ms(
                "market_query_candles_duration_ms",
                duration_ms=duration_ms,
                labels={"result": "ok"},
            )
            metrics.set_gauge(
                "market_query_candles_result_count",
                value=float(len(candles)),
                labels={"series_id": series_id},
            )
            if head_time is not None:
                metrics.set_gauge(
                    "market_query_head_time",
                    value=float(head_time),
                    labels={"series_id": series_id},
                )
                lag_seconds = max(0, int(time.time()) - int(head_time))
                metrics.set_gauge(
                    "market_query_head_lag_seconds",
                    value=float(lag_seconds),
                    labels={"series_id": series_id},
                )
        if bool(self.runtime_flags.enable_debug_api) and candles:
            last_time = int(candles[-1].candle_time)
            self.debug_hub.emit(
                pipe="read",
                event="read.http.market_candles",
                series_id=series_id,
                message="get market candles",
                data={
                    "since": None if since is None else int(since),
                    "limit": int(limit),
                    "count": int(len(candles)),
                    "last_time": int(last_time),
                    "server_head_time": None if head_time is None else int(head_time),
                },
            )
        return GetCandlesResponse(series_id=series_id, server_head_time=head_time, candles=candles)
