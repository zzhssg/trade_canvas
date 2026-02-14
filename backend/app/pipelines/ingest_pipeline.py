from __future__ import annotations

import time
from typing import Mapping, Sequence

from ..core.ports import CandleHubPort
from ..runtime.blocking import run_blocking
from ..core.schemas import CandleClosed
from ..storage.candle_store import CandleStore
from .ingest_pipeline_steps import (
    FactorOrchestratorLike,
    IngestPipelineError,
    IngestPipelineResult,
    IngestSeriesBatch,
    IngestStepResult,
    OverlayOrchestratorLike,
    merge_up_to_times,
    normalize_batches,
    persist_closed_batch,
    rollback_new_candles,
    run_factor_step,
    run_overlay_step,
)


class IngestPipeline:
    def __init__(
        self,
        *,
        store: CandleStore,
        factor_orchestrator: FactorOrchestratorLike | None,
        overlay_orchestrator: OverlayOrchestratorLike | None,
        hub: CandleHubPort | None,
        overlay_compensate_on_error: bool = False,
        candle_compensate_on_error: bool = False,
    ) -> None:
        self._store = store
        self._factor_orchestrator = factor_orchestrator
        self._overlay_orchestrator = overlay_orchestrator
        self._hub = hub
        self._overlay_compensate_on_error = bool(overlay_compensate_on_error)
        self._candle_compensate_on_error = bool(candle_compensate_on_error)

    def _rollback_new_candles(self, *, series_id: str, new_candle_times: list[int]) -> tuple[int, BaseException | None]:
        return rollback_new_candles(
            store=self._store,
            enabled=bool(self._candle_compensate_on_error),
            series_id=series_id,
            new_candle_times=new_candle_times,
        )

    @staticmethod
    def _normalize_batches(*, batches: Mapping[str, Sequence[CandleClosed]]) -> tuple[IngestSeriesBatch, ...]:
        return normalize_batches(batches=batches)

    def run_sync(
        self,
        *,
        batches: Mapping[str, Sequence[CandleClosed]],
    ) -> IngestPipelineResult:
        return self._run_sync(
            series_batches=self._normalize_batches(batches=batches),
            refresh_up_to_times={},
        )

    def refresh_series_sync(
        self,
        *,
        up_to_times: Mapping[str, int],
    ) -> IngestPipelineResult:
        refresh: dict[str, int] = {}
        for series_id, up_to in (up_to_times or {}).items():
            t = int(up_to or 0)
            if t <= 0:
                continue
            refresh[str(series_id)] = t
        return self._run_sync(
            series_batches=tuple(),
            refresh_up_to_times=refresh,
        )

    def _run_sync(
        self,
        *,
        series_batches: tuple[IngestSeriesBatch, ...],
        refresh_up_to_times: Mapping[str, int],
    ) -> IngestPipelineResult:
        t0 = time.perf_counter()
        steps: list[IngestStepResult] = []
        rebuilt_series: set[str] = set()

        up_to_by_series = merge_up_to_times(
            series_batches=series_batches,
            refresh_up_to_times=refresh_up_to_times,
        )
        series_batch_by_id = {batch.series_id: batch for batch in series_batches}

        for series_id in sorted(up_to_by_series.keys()):
            up_to_time = int(up_to_by_series[series_id])
            matched_batch = series_batch_by_id.get(series_id)
            new_candle_times: list[int] = []
            if matched_batch is not None and matched_batch.candles:
                new_candle_times, store_steps = persist_closed_batch(
                    store=self._store,
                    batch=matched_batch,
                )
                steps.extend(store_steps)

            if self._factor_orchestrator is not None:
                rebuilt, factor_step = run_factor_step(
                    factor_orchestrator=self._factor_orchestrator,
                    rollback_new_candles=self._rollback_new_candles,
                    series_id=series_id,
                    up_to_time=int(up_to_time),
                    new_candle_times=new_candle_times,
                )
                if rebuilt:
                    rebuilt_series.add(series_id)
                steps.append(factor_step)

            if self._overlay_orchestrator is not None:
                overlay_step = run_overlay_step(
                    overlay_orchestrator=self._overlay_orchestrator,
                    rollback_new_candles=self._rollback_new_candles,
                    overlay_compensate_on_error=bool(self._overlay_compensate_on_error),
                    series_id=series_id,
                    up_to_time=int(up_to_time),
                    rebuilt=bool(series_id in rebuilt_series),
                    new_candle_times=new_candle_times,
                )
                steps.append(overlay_step)

        return IngestPipelineResult(
            series_batches=series_batches,
            rebuilt_series=tuple(sorted(rebuilt_series)),
            steps=tuple(steps),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    async def run(
        self,
        *,
        batches: Mapping[str, Sequence[CandleClosed]],
        publish: bool = True,
    ) -> IngestPipelineResult:
        result = await run_blocking(self.run_sync, batches=batches)
        if publish:
            await self.publish(result=result)
        return result

    async def refresh_series(
        self,
        *,
        up_to_times: Mapping[str, int],
        publish_system_events: bool = True,
    ) -> IngestPipelineResult:
        result = await run_blocking(self.refresh_series_sync, up_to_times=up_to_times)
        if publish_system_events and result.rebuilt_series:
            await self.publish_system_rebuilds(result=result)
        return result

    async def publish(self, *, result: IngestPipelineResult, best_effort: bool = False) -> None:
        if self._hub is None:
            return
        for batch in result.series_batches:
            await self._publish_series_batch(batch=batch, best_effort=best_effort)
        await self.publish_system_rebuilds(result=result, best_effort=best_effort)

    async def publish_ws(
        self,
        *,
        result: IngestPipelineResult,
    ) -> None:
        if self._hub is None:
            return
        await self.publish(result=result, best_effort=True)

    async def publish_system_rebuilds(self, *, result: IngestPipelineResult, best_effort: bool = False) -> None:
        if self._hub is None:
            return
        for series_id in result.rebuilt_series:
            try:
                await self._hub.publish_system(
                    series_id=series_id,
                    event="factor.rebuild",
                    message="因子口径更新，已自动完成历史重算",
                    data={"series_id": series_id},
                )
            except Exception:
                if not best_effort:
                    raise

    async def _publish_series_batch(self, *, batch: IngestSeriesBatch, best_effort: bool) -> None:
        if self._hub is None:
            return
        candles = list(batch.candles)
        if not candles:
            return
        if len(candles) == 1:
            try:
                await self._hub.publish_closed(series_id=batch.series_id, candle=candles[0])
            except Exception:
                if not best_effort:
                    raise
            return

        try:
            await self._hub.publish_closed_batch(series_id=batch.series_id, candles=candles)
        except Exception:
            if not best_effort:
                raise
