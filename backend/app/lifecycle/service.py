from __future__ import annotations

from dataclasses import dataclass

from ..market.runtime import MarketRuntime
from .startup_kline_sync import run_startup_kline_sync_for_runtime


@dataclass(frozen=True)
class AppLifecycleService:
    market_runtime: MarketRuntime

    async def startup(self) -> None:
        runtime_flags = self.market_runtime.runtime_flags
        flags = self.market_runtime.flags
        hub = self.market_runtime.hub
        supervisor = self.market_runtime.ingest_ctx.supervisor
        start_pubsub = getattr(hub, "start_pubsub", None)
        if callable(start_pubsub):
            await start_pubsub()
        if bool(runtime_flags.enable_startup_kline_sync):
            await run_startup_kline_sync_for_runtime(
                runtime=self.market_runtime,
                enabled=bool(runtime_flags.enable_startup_kline_sync),
                target_candles=int(runtime_flags.startup_kline_sync_target_candles),
            )

        if bool(supervisor.whitelist_ingest_enabled):
            await supervisor.start_whitelist()

        if bool(supervisor.whitelist_ingest_enabled) or bool(flags.enable_ondemand_ingest):
            await supervisor.start_reaper()

    async def shutdown(self) -> None:
        hub = self.market_runtime.hub
        supervisor = self.market_runtime.ingest_ctx.supervisor
        close_pubsub = getattr(hub, "close_pubsub", None)
        if callable(close_pubsub):
            try:
                await close_pubsub()
            except Exception:
                pass
        try:
            await hub.close_all()
        except Exception:
            pass
        await supervisor.close()
