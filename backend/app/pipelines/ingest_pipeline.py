from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from ..blocking import run_blocking
from ..schemas import CandleClosed
from ..store import CandleStore


class _FactorIngestResultLike(Protocol):
    @property
    def rebuilt(self) -> bool: ...


class _FactorOrchestratorLike(Protocol):
    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> _FactorIngestResultLike: ...


class _OverlayOrchestratorLike(Protocol):
    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...

    def reset_series(self, *, series_id: str) -> None: ...


class _HubLike(Protocol):
    async def publish_closed(self, *, series_id: str, candle: CandleClosed) -> None: ...

    async def publish_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> None: ...

    async def publish_system(self, *, series_id: str, event: str, message: str, data: dict) -> None: ...


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


class IngestPipelineError(RuntimeError):
    def __init__(
        self,
        *,
        step: str,
        series_id: str,
        cause: BaseException,
        compensated: bool = False,
        compensation_error: BaseException | None = None,
        overlay_compensated: bool = False,
        candle_compensated_rows: int = 0,
    ) -> None:
        self.step = str(step)
        self.series_id = str(series_id)
        self.cause = cause
        self.compensated = bool(compensated)
        self.compensation_error = compensation_error
        self.overlay_compensated = bool(overlay_compensated)
        self.candle_compensated_rows = max(0, int(candle_compensated_rows))
        suffix = ":compensated" if self.compensated else ""
        if self.overlay_compensated:
            suffix = f"{suffix}:overlay_reset"
        if self.candle_compensated_rows > 0:
            suffix = f"{suffix}:candle_rows:{self.candle_compensated_rows}"
        if compensation_error is not None:
            suffix = f"{suffix}:compensation_error:{compensation_error}"
        super().__init__(f"ingest_pipeline_failed:{self.step}:{self.series_id}:{cause}{suffix}")


class IngestPipeline:
    def __init__(
        self,
        *,
        store: CandleStore,
        factor_orchestrator: _FactorOrchestratorLike | None,
        overlay_orchestrator: _OverlayOrchestratorLike | None,
        hub: _HubLike | None,
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
        if not self._candle_compensate_on_error:
            return 0, None
        if not new_candle_times:
            return 0, None
        try:
            with self._store.connect() as conn:
                deleted = self._store.delete_closed_times_in_conn(
                    conn,
                    series_id=series_id,
                    candle_times=list(new_candle_times),
                )
                conn.commit()
            return int(deleted), None
        except Exception as exc:
            return 0, exc

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
        series_batch_by_id = {batch.series_id: batch for batch in series_batches}

        for series_id in sorted(up_to_by_series.keys()):
            up_to_time = int(up_to_by_series[series_id])
            matched_batch = series_batch_by_id.get(series_id)
            new_candle_times: list[int] = []
            if matched_batch is not None and matched_batch.candles:
                t_step = time.perf_counter()
                try:
                    candle_times = [int(c.candle_time) for c in matched_batch.candles]
                    with self._store.connect() as conn:
                        existing_times = self._store.existing_closed_times_in_conn(
                            conn,
                            series_id=matched_batch.series_id,
                            candle_times=candle_times,
                        )
                        self._store.upsert_many_closed_in_conn(conn, matched_batch.series_id, list(matched_batch.candles))
                        conn.commit()
                    new_candle_times = [t for t in candle_times if int(t) not in existing_times]
                except Exception as exc:
                    raise IngestPipelineError(step="store.upsert_many_closed", series_id=series_id, cause=exc) from exc
                steps.append(
                    IngestStepResult(
                        name=f"store.upsert_many_closed:{series_id}",
                        ok=True,
                        duration_ms=int((time.perf_counter() - t_step) * 1000),
                    )
                )

            if self._factor_orchestrator is not None:
                t_step = time.perf_counter()
                try:
                    result = self._factor_orchestrator.ingest_closed(
                        series_id=series_id,
                        up_to_candle_time=int(up_to_time),
                    )
                except Exception as exc:
                    candle_rows, candle_error = self._rollback_new_candles(
                        series_id=series_id,
                        new_candle_times=new_candle_times,
                    )
                    raise IngestPipelineError(
                        step="factor.ingest_closed",
                        series_id=series_id,
                        cause=exc,
                        compensated=bool(candle_rows > 0),
                        compensation_error=candle_error,
                        candle_compensated_rows=int(candle_rows),
                    ) from exc
                if bool(getattr(result, "rebuilt", False)):
                    rebuilt_series.add(series_id)
                steps.append(
                    IngestStepResult(
                        name=f"factor.ingest_closed:{series_id}",
                        ok=True,
                        duration_ms=int((time.perf_counter() - t_step) * 1000),
                    )
                )

            if self._overlay_orchestrator is not None:
                t_step = time.perf_counter()
                try:
                    if series_id in rebuilt_series:
                        self._overlay_orchestrator.reset_series(series_id=series_id)
                    self._overlay_orchestrator.ingest_closed(
                        series_id=series_id,
                        up_to_candle_time=int(up_to_time),
                    )
                except Exception as exc:
                    overlay_compensated = False
                    candle_rows = 0
                    compensation_error: BaseException | None = None
                    if self._overlay_compensate_on_error:
                        try:
                            self._overlay_orchestrator.reset_series(series_id=series_id)
                            overlay_compensated = True
                        except Exception as rollback_exc:
                            compensation_error = rollback_exc
                    candle_rows, candle_error = self._rollback_new_candles(
                        series_id=series_id,
                        new_candle_times=new_candle_times,
                    )
                    if compensation_error is None:
                        compensation_error = candle_error
                    elif candle_error is not None:
                        compensation_error = RuntimeError(f"{compensation_error}; {candle_error}")
                    raise IngestPipelineError(
                        step="overlay.ingest_closed",
                        series_id=series_id,
                        cause=exc,
                        compensated=bool(overlay_compensated or candle_rows > 0),
                        compensation_error=compensation_error,
                        overlay_compensated=bool(overlay_compensated),
                        candle_compensated_rows=int(candle_rows),
                    ) from exc
                steps.append(
                    IngestStepResult(
                        name=f"overlay.ingest_closed:{series_id}",
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
        primary_series_id: str,
        unified_publish_enabled: bool,
    ) -> None:
        if self._hub is None:
            return
        if unified_publish_enabled:
            await self.publish(result=result, best_effort=True)
            return

        primary_batch: IngestSeriesBatch | None = None
        for batch in result.series_batches:
            if str(batch.series_id) == str(primary_series_id):
                primary_batch = batch
                break

        if primary_batch is not None:
            await self._publish_series_batch(batch=primary_batch, best_effort=False)

        for batch in result.series_batches:
            if primary_batch is not None and batch is primary_batch:
                continue
            await self._publish_series_batch(batch=batch, best_effort=True)

        await self.publish_system_rebuilds(result=result, best_effort=True)

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
