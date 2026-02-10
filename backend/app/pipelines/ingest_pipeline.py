from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..blocking import run_blocking
from ..factor_orchestrator import FactorOrchestrator
from ..overlay_orchestrator import OverlayOrchestrator
from ..schemas import CandleClosed
from ..store import CandleStore
from ..ws_hub import CandleHub


@dataclass(frozen=True)
class IngestStepResult:
    name: str
    ok: bool
    duration_ms: int
    error: str | None = None


@dataclass(frozen=True)
class IngestSeriesBatch:
    series_id: str
    candles: tuple[CandleClosed, ...]
    up_to_candle_time: int


@dataclass(frozen=True)
class IngestPipelineResult:
    series_batches: tuple[IngestSeriesBatch, ...]
    rebuilt_series: tuple[str, ...]
    steps: tuple[IngestStepResult, ...]
    duration_ms: int


class IngestPipeline:
    def __init__(
        self,
        *,
        store: CandleStore,
        factor_orchestrator: FactorOrchestrator | None,
        overlay_orchestrator: OverlayOrchestrator | None,
        hub: CandleHub | None,
    ) -> None:
        self._store = store
        self._factor_orchestrator = factor_orchestrator
        self._overlay_orchestrator = overlay_orchestrator
        self._hub = hub

    @staticmethod
    def _normalize_batches(*, batches: Mapping[str, Sequence[CandleClosed]]) -> tuple[IngestSeriesBatch, ...]:
        out: list[IngestSeriesBatch] = []
        for series_id, candles in sorted((batches or {}).items(), key=lambda item: str(item[0])):
            dedup: dict[int, CandleClosed] = {}
            for candle in candles or ():
                dedup[int(candle.candle_time)] = candle
            ordered = tuple(dedup[t] for t in sorted(dedup.keys()))
            if not ordered:
                continue
            out.append(
                IngestSeriesBatch(
                    series_id=str(series_id),
                    candles=ordered,
                    up_to_candle_time=int(ordered[-1].candle_time),
                )
            )
        return tuple(out)

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

        up_to_by_series: dict[str, int] = {}
        for batch in series_batches:
            up_to_by_series[batch.series_id] = int(batch.up_to_candle_time)
        for series_id, up_to in (refresh_up_to_times or {}).items():
            sid = str(series_id)
            t = int(up_to)
            if t <= 0:
                continue
            current = up_to_by_series.get(sid)
            up_to_by_series[sid] = t if current is None else max(int(current), t)

        if series_batches:
            t_step = time.perf_counter()
            with self._store.connect() as conn:
                for batch in series_batches:
                    self._store.upsert_many_closed_in_conn(conn, batch.series_id, list(batch.candles))
                conn.commit()
            steps.append(
                IngestStepResult(
                    name="store.upsert_many_closed",
                    ok=True,
                    duration_ms=int((time.perf_counter() - t_step) * 1000),
                )
            )

        if self._factor_orchestrator is not None and up_to_by_series:
            t_step = time.perf_counter()
            for series_id in sorted(up_to_by_series.keys()):
                result = self._factor_orchestrator.ingest_closed(
                    series_id=series_id,
                    up_to_candle_time=int(up_to_by_series[series_id]),
                )
                if bool(getattr(result, "rebuilt", False)):
                    rebuilt_series.add(series_id)
            steps.append(
                IngestStepResult(
                    name="factor.ingest_closed",
                    ok=True,
                    duration_ms=int((time.perf_counter() - t_step) * 1000),
                )
            )

        if self._overlay_orchestrator is not None and up_to_by_series:
            t_step = time.perf_counter()
            for series_id in sorted(up_to_by_series.keys()):
                if series_id in rebuilt_series:
                    self._overlay_orchestrator.reset_series(series_id=series_id)
                self._overlay_orchestrator.ingest_closed(
                    series_id=series_id,
                    up_to_candle_time=int(up_to_by_series[series_id]),
                )
            steps.append(
                IngestStepResult(
                    name="overlay.ingest_closed",
                    ok=True,
                    duration_ms=int((time.perf_counter() - t_step) * 1000),
                )
            )

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

    async def publish(self, *, result: IngestPipelineResult) -> None:
        if self._hub is None:
            return
        for batch in result.series_batches:
            await self._hub.publish_closed_batch(series_id=batch.series_id, candles=list(batch.candles))
        await self.publish_system_rebuilds(result=result)

    async def publish_system_rebuilds(self, *, result: IngestPipelineResult) -> None:
        if self._hub is None:
            return
        for series_id in result.rebuilt_series:
            await self._hub.publish_system(
                series_id=series_id,
                event="factor.rebuild",
                message="因子口径更新，已自动完成历史重算",
                data={"series_id": series_id},
            )
