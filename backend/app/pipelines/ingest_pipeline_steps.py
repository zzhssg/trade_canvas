from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ..core.schemas import CandleClosed


class FactorIngestResultLike(Protocol):
    @property
    def rebuilt(self) -> bool: ...


class FactorOrchestratorLike(Protocol):
    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> FactorIngestResultLike: ...


class OverlayOrchestratorLike(Protocol):
    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...

    def reset_series(self, *, series_id: str) -> None: ...


class IngestStoreLike(Protocol):
    def connect(self) -> Any: ...

    def existing_closed_times_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        candle_times: list[int],
    ) -> set[int]: ...

    def upsert_many_closed_in_conn(
        self,
        conn: Any,
        series_id: str,
        candles: list[CandleClosed],
    ) -> None: ...

    def delete_closed_times_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        candle_times: list[int],
    ) -> int: ...


class RollbackNewCandlesFn(Protocol):
    def __call__(
        self,
        *,
        series_id: str,
        new_candle_times: list[int],
    ) -> tuple[int, BaseException | None]: ...


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


def normalize_batches(*, batches: Mapping[str, Sequence[CandleClosed]]) -> tuple[IngestSeriesBatch, ...]:
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


def merge_up_to_times(
    *,
    series_batches: tuple[IngestSeriesBatch, ...],
    refresh_up_to_times: Mapping[str, int],
) -> dict[str, int]:
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
    return up_to_by_series


def rollback_new_candles(
    *,
    store: IngestStoreLike,
    enabled: bool,
    series_id: str,
    new_candle_times: list[int],
) -> tuple[int, BaseException | None]:
    if not bool(enabled):
        return 0, None
    if not new_candle_times:
        return 0, None
    try:
        with store.connect() as conn:
            deleted = store.delete_closed_times_in_conn(
                conn,
                series_id=series_id,
                candle_times=list(new_candle_times),
            )
            conn.commit()
        return int(deleted), None
    except Exception as exc:
        return 0, exc


def persist_closed_batch(
    *,
    store: IngestStoreLike,
    batch: IngestSeriesBatch,
) -> tuple[list[int], tuple[IngestStepResult, ...]]:
    t_step = time.perf_counter()
    try:
        candle_times = [int(c.candle_time) for c in batch.candles]
        with store.connect() as conn:
            existing_times = store.existing_closed_times_in_conn(
                conn,
                series_id=batch.series_id,
                candle_times=candle_times,
            )
            store.upsert_many_closed_in_conn(conn, batch.series_id, list(batch.candles))
            conn.commit()
        new_candle_times = [t for t in candle_times if int(t) not in existing_times]
    except Exception as exc:
        raise IngestPipelineError(
            step="store.upsert_many_closed",
            series_id=batch.series_id,
            cause=exc,
        ) from exc

    steps: list[IngestStepResult] = [
        IngestStepResult(
            name=f"store.upsert_many_closed:{batch.series_id}",
            ok=True,
            duration_ms=int((time.perf_counter() - t_step) * 1000),
        )
    ]
    return new_candle_times, tuple(steps)


def run_factor_step(
    *,
    factor_orchestrator: FactorOrchestratorLike,
    rollback_new_candles: RollbackNewCandlesFn,
    series_id: str,
    up_to_time: int,
    new_candle_times: list[int],
) -> tuple[bool, IngestStepResult]:
    t_step = time.perf_counter()
    try:
        result = factor_orchestrator.ingest_closed(
            series_id=series_id,
            up_to_candle_time=int(up_to_time),
        )
    except Exception as exc:
        candle_rows, candle_error = rollback_new_candles(
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

    rebuilt = bool(getattr(result, "rebuilt", False))
    return rebuilt, IngestStepResult(
        name=f"factor.ingest_closed:{series_id}",
        ok=True,
        duration_ms=int((time.perf_counter() - t_step) * 1000),
    )


def run_overlay_step(
    *,
    overlay_orchestrator: OverlayOrchestratorLike,
    rollback_new_candles: RollbackNewCandlesFn,
    overlay_compensate_on_error: bool,
    series_id: str,
    up_to_time: int,
    rebuilt: bool,
    new_candle_times: list[int],
) -> IngestStepResult:
    t_step = time.perf_counter()
    try:
        if rebuilt:
            overlay_orchestrator.reset_series(series_id=series_id)
        overlay_orchestrator.ingest_closed(
            series_id=series_id,
            up_to_candle_time=int(up_to_time),
        )
    except Exception as exc:
        overlay_compensated = False
        candle_rows = 0
        compensation_error: BaseException | None = None
        if bool(overlay_compensate_on_error):
            try:
                overlay_orchestrator.reset_series(series_id=series_id)
                overlay_compensated = True
            except Exception as rollback_exc:
                compensation_error = rollback_exc
        candle_rows, candle_error = rollback_new_candles(
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

    return IngestStepResult(
        name=f"overlay.ingest_closed:{series_id}",
        ok=True,
        duration_ms=int((time.perf_counter() - t_step) * 1000),
    )
