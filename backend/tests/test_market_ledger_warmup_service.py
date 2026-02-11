from __future__ import annotations

import unittest
from typing import Mapping

from backend.app.market_ledger_warmup_service import MarketLedgerWarmupService


class _RuntimeFlagsStub:
    def __init__(
        self,
        *,
        enable_read_ledger_warmup: bool,
        enable_debug_api: bool,
        enable_ledger_sync_service: bool = False,
    ) -> None:
        self.enable_read_ledger_warmup = bool(enable_read_ledger_warmup)
        self.enable_debug_api = bool(enable_debug_api)
        self.enable_ledger_sync_service = bool(enable_ledger_sync_service)


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


class _HeadStoreStub:
    def __init__(self, *, head_time: int | None) -> None:
        self._head_time = None if head_time is None else int(head_time)
        self.calls: list[str] = []

    def head_time(self, series_id: str) -> int | None:
        self.calls.append(str(series_id))
        return None if self._head_time is None else int(self._head_time)


class _StepStub:
    def __init__(self, name: str) -> None:
        self.name = str(name)


class _RefreshResultStub:
    def __init__(self, *, steps: tuple[_StepStub, ...]) -> None:
        self.steps = tuple(steps)


class _IngestPipelineStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, int]] = []

    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]) -> _RefreshResultStub:
        self.calls.append({str(k): int(v) for k, v in up_to_times.items()})
        return _RefreshResultStub(steps=(_StepStub("factor.ingest_closed:test"),))


class _LedgerSnapshotStub:
    def __init__(self, *, factor_head_time: int | None, overlay_head_time: int | None) -> None:
        self.factor_head_time = factor_head_time
        self.overlay_head_time = overlay_head_time


class _LedgerRefreshOutcomeStub:
    def __init__(self, *, refreshed: bool, step_names: tuple[str, ...], factor_head_time: int | None, overlay_head_time: int | None) -> None:
        self.refreshed = bool(refreshed)
        self.step_names = tuple(step_names)
        self.factor_head_time = factor_head_time
        self.overlay_head_time = overlay_head_time


class _LedgerSyncStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def head_snapshot(self, *, series_id: str) -> _LedgerSnapshotStub:
        _ = series_id
        return _LedgerSnapshotStub(factor_head_time=200, overlay_head_time=200)

    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> _LedgerRefreshOutcomeStub:
        self.calls.append((str(series_id), int(up_to_time)))
        return _LedgerRefreshOutcomeStub(
            refreshed=False,
            step_names=tuple(),
            factor_head_time=200,
            overlay_head_time=200,
        )


class MarketLedgerWarmupServiceTests(unittest.TestCase):
    def test_warmup_refreshes_ledgers_when_heads_lagging(self) -> None:
        pipeline = _IngestPipelineStub()
        debug_hub = _DebugHubStub()
        service = MarketLedgerWarmupService(
            factor_store=_HeadStoreStub(head_time=None),
            overlay_store=_HeadStoreStub(head_time=120),
            ingest_pipeline=pipeline,
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=True),
            debug_hub=debug_hub,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(pipeline.calls, [{"binance:spot:ETH/USDT:1d": 160}])
        self.assertTrue(
            any(event.get("event") == "read.http.market_candles_ledger_warmup" for event in debug_hub.events),
            "expected warmup debug event",
        )

    def test_warmup_skips_when_flag_disabled(self) -> None:
        pipeline = _IngestPipelineStub()
        service = MarketLedgerWarmupService(
            factor_store=_HeadStoreStub(head_time=None),
            overlay_store=_HeadStoreStub(head_time=None),
            ingest_pipeline=pipeline,
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=False, enable_debug_api=True),
            debug_hub=_DebugHubStub(),
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(pipeline.calls, [])

    def test_warmup_skips_when_ledgers_already_caught_up(self) -> None:
        pipeline = _IngestPipelineStub()
        service = MarketLedgerWarmupService(
            factor_store=_HeadStoreStub(head_time=200),
            overlay_store=_HeadStoreStub(head_time=180),
            ingest_pipeline=pipeline,
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=True),
            debug_hub=_DebugHubStub(),
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(pipeline.calls, [])

    def test_warmup_uses_ledger_sync_service_when_flag_enabled(self) -> None:
        pipeline = _IngestPipelineStub()
        ledger_sync = _LedgerSyncStub()
        service = MarketLedgerWarmupService(
            factor_store=_HeadStoreStub(head_time=200),
            overlay_store=_HeadStoreStub(head_time=200),
            ingest_pipeline=pipeline,
            runtime_flags=_RuntimeFlagsStub(
                enable_read_ledger_warmup=True,
                enable_debug_api=True,
                enable_ledger_sync_service=True,
            ),
            debug_hub=_DebugHubStub(),
            ledger_sync_service=ledger_sync,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(ledger_sync.calls, [("binance:spot:ETH/USDT:1d", 160)])
        self.assertEqual(pipeline.calls, [])


if __name__ == "__main__":
    unittest.main()
