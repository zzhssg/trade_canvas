from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.ingest.job_runner import IngestJobRunner, IngestJobRunnerConfig
from backend.app.ingest.settings import WhitelistIngestSettings
from backend.app.store import CandleStore
from backend.app.ws.hub import CandleHub


class _FakeGuardrail:
    def __init__(self, *, wait_s: float) -> None:
        self._wait_s = float(wait_s)
        self.success_calls = 0
        self.failure_calls = 0

    def on_success(self) -> None:
        self.success_calls += 1

    def on_failure(self, *, error: Exception) -> float:
        _ = error
        self.failure_calls += 1
        return float(self._wait_s)


def _build_runner(tmp_path: Path) -> IngestJobRunner:
    store = CandleStore(db_path=tmp_path / "market.db")
    hub = CandleHub()
    return IngestJobRunner(
        store=store,
        hub=hub,
        ingest_pipeline=None,
        settings=WhitelistIngestSettings(),
        config=IngestJobRunnerConfig(
            market_history_source="",
            derived_enabled=False,
            derived_base_timeframe="1m",
            derived_timeframes=(),
            batch_max=200,
            flush_s=0.5,
            forming_min_interval_ms=250,
        ),
    )


def test_runner_success_calls_guardrail_success(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)
    stop = asyncio.Event()
    guardrail = _FakeGuardrail(wait_s=0.0)
    crashes: list[str] = []

    async def _ingest_fn(**kwargs) -> None:  # noqa: ANN003
        _ = kwargs

    async def _on_crash(series_id: str) -> None:
        crashes.append(series_id)

    async def _run() -> None:
        task = runner.start(
            series_id="binance:spot:BTC/USDT:1m",
            stop=stop,
            guardrail=guardrail,  # type: ignore[arg-type]
            ingest_fn=_ingest_fn,
            on_crash=_on_crash,
        )
        await task

    asyncio.run(_run())
    assert guardrail.success_calls == 1
    assert guardrail.failure_calls == 0
    assert crashes == []


def test_runner_failure_calls_crash_hook_and_guardrail_failure(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)
    stop = asyncio.Event()
    guardrail = _FakeGuardrail(wait_s=0.0)
    crashes: list[str] = []
    series_id = "binance:spot:ETH/USDT:1m"

    async def _failing_ingest_fn(**kwargs) -> None:  # noqa: ANN003
        _ = kwargs
        raise RuntimeError("ws loop failed")

    async def _on_crash(sid: str) -> None:
        crashes.append(sid)

    async def _run() -> None:
        task = runner.start(
            series_id=series_id,
            stop=stop,
            guardrail=guardrail,  # type: ignore[arg-type]
            ingest_fn=_failing_ingest_fn,
            on_crash=_on_crash,
        )
        await task

    asyncio.run(_run())
    assert guardrail.success_calls == 0
    assert guardrail.failure_calls == 1
    assert crashes == [series_id]
