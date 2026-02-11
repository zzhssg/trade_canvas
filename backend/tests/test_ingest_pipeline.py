from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.pipelines import IngestPipeline, IngestPipelineError
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class _Factor:
    def __init__(self, *, rebuilt_series: set[str] | None = None, fail_series: set[str] | None = None) -> None:
        self._rebuilt_series = set(rebuilt_series or set())
        self._fail_series = set(fail_series or set())
        self.calls: list[tuple[str, int]] = []

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int):
        if str(series_id) in self._fail_series:
            raise RuntimeError(f"factor_failed:{series_id}")
        self.calls.append((str(series_id), int(up_to_candle_time)))
        return SimpleNamespace(rebuilt=str(series_id) in self._rebuilt_series)


class _Overlay:
    def __init__(self) -> None:
        self.reset_calls: list[str] = []
        self.ingest_calls: list[tuple[str, int]] = []

    def reset_series(self, *, series_id: str) -> None:
        self.reset_calls.append(str(series_id))

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        self.ingest_calls.append((str(series_id), int(up_to_candle_time)))


class _OverlayFailing(_Overlay):
    def __init__(self, *, fail_series: set[str]) -> None:
        super().__init__()
        self._fail_series = set(fail_series)

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        if str(series_id) in self._fail_series:
            raise RuntimeError(f"overlay_failed:{series_id}:{up_to_candle_time}")
        super().ingest_closed(series_id=series_id, up_to_candle_time=up_to_candle_time)


class _Hub:
    def __init__(self) -> None:
        self.closed_batches: list[tuple[str, list[int]]] = []
        self.system_events: list[str] = []

    async def publish_closed(self, *, series_id: str, candle: CandleClosed) -> None:
        self.closed_batches.append((str(series_id), [int(candle.candle_time)]))

    async def publish_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> None:
        self.closed_batches.append((str(series_id), [int(c.candle_time) for c in candles]))

    async def publish_system(self, *, series_id: str, event: str, message: str, data: dict) -> None:
        _ = event
        _ = message
        _ = data
        self.system_events.append(str(series_id))


def _candle(t: int, price: float = 1.0) -> CandleClosed:
    return CandleClosed(candle_time=int(t), open=price, high=price, low=price, close=price, volume=1.0)


def test_ingest_pipeline_run_sync_persists_and_drives_sidecars() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series={"s1"})
        overlay = _Overlay()
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=None,
        )

        result = pipeline.run_sync(
            batches={
                "s1": [_candle(100, 1.0), _candle(100, 2.0), _candle(160, 3.0)],
                "s2": [_candle(200, 5.0)],
            }
        )

        s1 = store.get_closed("s1", since=None, limit=10)
        assert [int(c.candle_time) for c in s1] == [100, 160]
        assert [float(c.close) for c in s1] == [2.0, 3.0]

        assert factor.calls == [("s1", 160), ("s2", 200)]
        assert overlay.reset_calls == ["s1"]
        assert overlay.ingest_calls == [("s1", 160), ("s2", 200)]
        assert result.rebuilt_series == ("s1",)
        assert any(step.name.startswith("store.upsert_many_closed:") for step in result.steps)


def test_ingest_pipeline_refresh_series_sync_only_runs_sidecars() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series=set())
        overlay = _Overlay()
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=None,
        )

        result = pipeline.refresh_series_sync(up_to_times={"s1": 300})

        assert store.head_time("s1") is None
        assert factor.calls == [("s1", 300)]
        assert overlay.ingest_calls == [("s1", 300)]
        assert result.rebuilt_series == ()


def test_ingest_pipeline_run_publishes_batches_and_rebuild_system_events() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series={"s1"})
        overlay = _Overlay()
        hub = _Hub()
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=hub,
        )

        asyncio.run(
            pipeline.run(
                batches={"s1": [_candle(100, 1.0), _candle(160, 1.1)]},
                publish=True,
            )
        )

        assert hub.closed_batches == [("s1", [100, 160])]
        assert hub.system_events == ["s1"]


def test_ingest_pipeline_error_contains_step_and_series_context() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series=set(), fail_series={"s1"})
        overlay = _Overlay()
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=None,
        )

        with pytest.raises(IngestPipelineError) as exc:
            pipeline.run_sync(
                batches={
                    "s1": [_candle(100, 1.0)],
                    "s2": [_candle(200, 2.0)],
                }
            )

        assert exc.value.step == "factor.ingest_closed"
        assert exc.value.series_id == "s1"
        assert store.head_time("s2") is None


def test_ingest_pipeline_overlay_failure_can_compensate_by_resetting_series() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series=set())
        overlay = _OverlayFailing(fail_series={"s1"})
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=None,
            overlay_compensate_on_error=True,
        )

        with pytest.raises(IngestPipelineError) as exc:
            pipeline.run_sync(
                batches={
                    "s1": [_candle(100, 1.0)],
                }
            )

        assert exc.value.step == "overlay.ingest_closed"
        assert exc.value.series_id == "s1"
        assert exc.value.compensated is True
        assert exc.value.overlay_compensated is True
        assert exc.value.candle_compensated_rows == 0
        assert exc.value.compensation_error is None
        assert overlay.reset_calls == ["s1"]


def test_ingest_pipeline_factor_failure_can_compensate_new_candles() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        factor = _Factor(rebuilt_series=set(), fail_series={"s1"})
        overlay = _Overlay()
        pipeline = IngestPipeline(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            hub=None,
            candle_compensate_on_error=True,
        )

        with pytest.raises(IngestPipelineError) as exc:
            pipeline.run_sync(
                batches={
                    "s1": [_candle(100, 1.0)],
                }
            )

        assert exc.value.step == "factor.ingest_closed"
        assert exc.value.series_id == "s1"
        assert exc.value.compensated is True
        assert exc.value.overlay_compensated is False
        assert exc.value.candle_compensated_rows == 1
        assert exc.value.compensation_error is None
        assert store.head_time("s1") is None
