from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.app.startup_kline_sync import run_startup_kline_sync, run_startup_kline_sync_for_runtime


class _FakeStore:
    def __init__(self, *, heads: dict[str, int | None] | None = None) -> None:
        self.heads = dict(heads or {})

    def head_time(self, series_id: str) -> int | None:
        value = self.heads.get(str(series_id))
        if value is None:
            return None
        return int(value)


class _FakeBackfill:
    def __init__(self, *, store: _FakeStore, lag_by_series: dict[str, int] | None = None) -> None:
        self._store = store
        self._lag_by_series = dict(lag_by_series or {})
        self.calls: list[tuple[str, int, int | None]] = []

    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int:
        self.calls.append((str(series_id), int(target_candles), None if to_time is None else int(to_time)))
        if to_time is not None:
            lag = max(0, int(self._lag_by_series.get(str(series_id), 0)))
            self._store.heads[str(series_id)] = max(0, int(to_time) - int(lag))
        return int(target_candles)


class _FakePipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, int]] = []

    def refresh_series_sync(self, *, up_to_times: dict[str, int]):
        self.calls.append({str(k): int(v) for k, v in dict(up_to_times).items()})
        return object()


class _FakeDebugHub:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None:
        _ = level
        _ = message
        _ = series_id
        _ = data
        self.events.append((str(pipe), str(event)))


@dataclass(frozen=True)
class _FakeWhitelist:
    series_ids: tuple[str, ...]


@dataclass(frozen=True)
class _FakeRuntime:
    store: _FakeStore
    backfill: _FakeBackfill
    ingest_pipeline: _FakePipeline
    whitelist: _FakeWhitelist
    debug_hub: _FakeDebugHub


async def _inline_run_blocking(fn, /, *args, **kwargs):  # noqa: ANN001
    return fn(*args, **kwargs)


def test_startup_kline_sync_disabled_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.startup_kline_sync.run_blocking", _inline_run_blocking)
    store = _FakeStore(heads={"binance:futures:BTC/USDT:1m": 0})
    backfill = _FakeBackfill(store=store)
    pipeline = _FakePipeline()

    result = asyncio.run(
        run_startup_kline_sync(
            store=store,
            backfill=backfill,
            ingest_pipeline=pipeline,
            series_ids=("binance:futures:BTC/USDT:1m",),
            enabled=False,
            target_candles=2000,
        )
    )

    assert result.enabled is False
    assert result.series_total == 1
    assert result.series_results == tuple()
    assert backfill.calls == []
    assert pipeline.calls == []


def test_startup_kline_sync_updates_whitelist_series_and_marks_lagging(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.startup_kline_sync.run_blocking", _inline_run_blocking)
    series_1m = "binance:futures:BTC/USDT:1m"
    series_5m = "binance:futures:BTC/USDT:5m"
    store = _FakeStore(heads={series_1m: 0, series_5m: 0})
    backfill = _FakeBackfill(store=store, lag_by_series={series_5m: 300})
    pipeline = _FakePipeline()
    debug_hub = _FakeDebugHub()

    result = asyncio.run(
        run_startup_kline_sync(
            store=store,
            backfill=backfill,
            ingest_pipeline=pipeline,
            series_ids=(series_1m, series_5m),
            enabled=True,
            target_candles=500,
            debug_hub=debug_hub,
            now_time=3601,
        )
    )

    assert result.enabled is True
    assert result.series_total == 2
    assert result.series_synced == 1
    assert result.series_lagging == 1
    assert result.series_errors == 0
    assert sorted(backfill.calls) == sorted(
        [
            (series_1m, 500, 3540),
            (series_5m, 500, 3300),
        ]
    )
    assert sorted(pipeline.calls, key=lambda item: next(iter(item.keys()))) == sorted(
        [
            {series_1m: 3540},
            {series_5m: 3300},
        ],
        key=lambda item: next(iter(item.keys())),
    )
    assert len(debug_hub.events) == 3
    assert debug_hub.events[-1] == ("write", "write.startup.kline_sync.done")


def test_startup_kline_sync_for_runtime_uses_whitelist_series(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.startup_kline_sync.run_blocking", _inline_run_blocking)
    series_id = "binance:futures:ETH/USDT:1m"
    store = _FakeStore(heads={series_id: 0})
    backfill = _FakeBackfill(store=store)
    pipeline = _FakePipeline()
    debug_hub = _FakeDebugHub()
    runtime = _FakeRuntime(
        store=store,
        backfill=backfill,
        ingest_pipeline=pipeline,
        whitelist=_FakeWhitelist(series_ids=(series_id,)),
        debug_hub=debug_hub,
    )

    result = asyncio.run(
        run_startup_kline_sync_for_runtime(
            runtime=runtime,
            enabled=True,
            target_candles=600,
        )
    )

    assert result.series_total == 1
    assert len(backfill.calls) == 1
    assert backfill.calls[0][0] == series_id

