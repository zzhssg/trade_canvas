from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.app.lifecycle.service import AppLifecycleService


class _FakeSupervisor:
    def __init__(self, *, whitelist_ingest_enabled: bool = False) -> None:
        self.started_whitelist = 0
        self.started_reaper = 0
        self.closed = 0
        self.whitelist_ingest_enabled = bool(whitelist_ingest_enabled)

    async def start_whitelist(self) -> None:
        self.started_whitelist += 1

    async def start_reaper(self) -> None:
        self.started_reaper += 1

    async def close(self) -> None:
        self.closed += 1


class _FakeHub:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.fail_close = bool(fail_close)
        self.closed = 0

    async def close_all(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("close_failed")


@dataclass(frozen=True)
class _FakeRuntimeFlags:
    enable_startup_kline_sync: bool
    startup_kline_sync_target_candles: int
    enable_ondemand_ingest: bool = False


@dataclass(frozen=True)
class _FakeIngestCtx:
    supervisor: _FakeSupervisor


@dataclass(frozen=True)
class _FakeRuntime:
    runtime_flags: _FakeRuntimeFlags
    ingest_ctx: _FakeIngestCtx
    hub: _FakeHub


def test_lifecycle_startup_delegates_sync_and_supervisor(monkeypatch) -> None:
    calls: list[tuple[bool, int]] = []

    async def _fake_sync(*, runtime, enabled: bool, target_candles: int):  # noqa: ANN001
        _ = runtime
        calls.append((bool(enabled), int(target_candles)))
        return object()

    monkeypatch.setattr("backend.app.lifecycle.service.run_startup_kline_sync_for_runtime", _fake_sync)
    supervisor = _FakeSupervisor(whitelist_ingest_enabled=True)
    runtime = _FakeRuntime(
        runtime_flags=_FakeRuntimeFlags(enable_startup_kline_sync=True, startup_kline_sync_target_candles=700),
        ingest_ctx=_FakeIngestCtx(supervisor=supervisor),
        hub=_FakeHub(),
    )
    lifecycle = AppLifecycleService(market_runtime=runtime)  # type: ignore[arg-type]

    asyncio.run(lifecycle.startup())

    assert calls == [(True, 700)]
    assert supervisor.started_whitelist == 1
    assert supervisor.started_reaper == 1


def test_lifecycle_startup_ondemand_can_start_reaper_without_whitelist(monkeypatch) -> None:
    async def _fake_sync(*, runtime, enabled: bool, target_candles: int):  # noqa: ANN001
        _ = runtime
        _ = enabled
        _ = target_candles
        return object()

    monkeypatch.setattr("backend.app.lifecycle.service.run_startup_kline_sync_for_runtime", _fake_sync)
    supervisor = _FakeSupervisor(whitelist_ingest_enabled=False)
    runtime = _FakeRuntime(
        runtime_flags=_FakeRuntimeFlags(
            enable_startup_kline_sync=False,
            startup_kline_sync_target_candles=2000,
            enable_ondemand_ingest=True,
        ),
        ingest_ctx=_FakeIngestCtx(supervisor=supervisor),
        hub=_FakeHub(),
    )
    lifecycle = AppLifecycleService(market_runtime=runtime)  # type: ignore[arg-type]

    asyncio.run(lifecycle.startup())

    assert supervisor.started_whitelist == 0
    assert supervisor.started_reaper == 1


def test_lifecycle_shutdown_closes_supervisor_when_hub_close_fails() -> None:
    supervisor = _FakeSupervisor(whitelist_ingest_enabled=False)
    hub = _FakeHub(fail_close=True)
    runtime = _FakeRuntime(
        runtime_flags=_FakeRuntimeFlags(enable_startup_kline_sync=False, startup_kline_sync_target_candles=2000),
        ingest_ctx=_FakeIngestCtx(supervisor=supervisor),
        hub=hub,
    )
    lifecycle = AppLifecycleService(market_runtime=runtime)  # type: ignore[arg-type]

    asyncio.run(lifecycle.shutdown())

    assert hub.closed == 1
    assert supervisor.closed == 1
