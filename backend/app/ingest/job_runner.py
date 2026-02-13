from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from .loop_guardrail import IngestLoopGuardrail
from .settings import WhitelistIngestSettings
from ..pipelines import IngestPipeline
from ..store import CandleStore
from ..ws.hub import CandleHub

IngestLoopFn = Callable[..., Awaitable[None]]
JobCrashHook = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class IngestJobRunnerConfig:
    market_history_source: str
    derived_enabled: bool
    derived_base_timeframe: str
    derived_timeframes: tuple[str, ...]
    batch_max: int
    flush_s: float
    forming_min_interval_ms: int


class IngestJobRunner:
    def __init__(
        self,
        *,
        store: CandleStore,
        hub: CandleHub,
        ingest_pipeline: IngestPipeline | None,
        settings: WhitelistIngestSettings,
        config: IngestJobRunnerConfig,
    ) -> None:
        self._store = store
        self._hub = hub
        self._ingest_pipeline = ingest_pipeline
        self._settings = settings
        self._config = config

    def start(
        self,
        *,
        series_id: str,
        stop: asyncio.Event,
        guardrail: IngestLoopGuardrail | None,
        ingest_fn: IngestLoopFn,
        on_crash: JobCrashHook,
    ) -> asyncio.Task:
        config = self._config

        async def runner() -> None:
            try:
                await ingest_fn(
                    series_id=series_id,
                    store=self._store,
                    hub=self._hub,
                    ingest_pipeline=self._ingest_pipeline,
                    settings=self._settings,
                    stop=stop,
                    market_history_source=config.market_history_source,
                    derived_enabled=config.derived_enabled,
                    derived_base_timeframe=config.derived_base_timeframe,
                    derived_timeframes=config.derived_timeframes,
                    batch_max=config.batch_max,
                    flush_s=config.flush_s,
                    forming_min_interval_ms=config.forming_min_interval_ms,
                    loop_guardrail=guardrail,
                )
                if guardrail is not None:
                    guardrail.on_success()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await on_crash(series_id)
                wait_s = 2.0
                if guardrail is not None:
                    wait_s = max(0.0, float(guardrail.on_failure(error=exc)))
                if wait_s <= 0:
                    return
                try:
                    await asyncio.wait_for(stop.wait(), timeout=float(wait_s))
                except asyncio.TimeoutError:
                    pass

        return asyncio.create_task(runner())
