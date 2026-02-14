from __future__ import annotations

import unittest

from backend.app.market.ledger_warmup_service import MarketLedgerWarmupService


class _RuntimeFlagsStub:
    def __init__(
        self,
        *,
        enable_read_ledger_warmup: bool,
        enable_debug_api: bool,
    ) -> None:
        self.enable_read_ledger_warmup = bool(enable_read_ledger_warmup)
        self.enable_debug_api = bool(enable_debug_api)


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


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
    def __init__(self, *, fail_refresh: bool = False) -> None:
        self.fail_refresh = bool(fail_refresh)
        self.calls: list[tuple[str, int]] = []

    def head_snapshot(self, *, series_id: str) -> _LedgerSnapshotStub:
        _ = series_id
        return _LedgerSnapshotStub(factor_head_time=120, overlay_head_time=100)

    def refresh_if_needed(self, *, series_id: str, up_to_time: int) -> _LedgerRefreshOutcomeStub:
        self.calls.append((str(series_id), int(up_to_time)))
        if self.fail_refresh:
            raise RuntimeError("refresh_failed")
        return _LedgerRefreshOutcomeStub(
            refreshed=True,
            step_names=("factor.ingest_closed:test", "overlay.ingest_closed:test"),
            factor_head_time=int(up_to_time),
            overlay_head_time=int(up_to_time),
        )


class MarketLedgerWarmupServiceTests(unittest.TestCase):
    def test_warmup_refreshes_ledgers_when_enabled(self) -> None:
        ledger_sync = _LedgerSyncStub()
        debug_hub = _DebugHubStub()
        service = MarketLedgerWarmupService(
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=True),
            debug_hub=debug_hub,
            ledger_sync_service=ledger_sync,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(ledger_sync.calls, [("binance:spot:ETH/USDT:1d", 160)])
        self.assertTrue(
            any(event.get("event") == "read.http.market_candles_ledger_warmup" for event in debug_hub.events),
            "expected warmup debug event",
        )

    def test_warmup_skips_when_flag_disabled(self) -> None:
        ledger_sync = _LedgerSyncStub()
        service = MarketLedgerWarmupService(
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=False, enable_debug_api=True),
            debug_hub=_DebugHubStub(),
            ledger_sync_service=ledger_sync,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(ledger_sync.calls, [])

    def test_warmup_skips_when_store_head_missing(self) -> None:
        ledger_sync = _LedgerSyncStub()
        service = MarketLedgerWarmupService(
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=True),
            debug_hub=_DebugHubStub(),
            ledger_sync_service=ledger_sync,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=None,
        )

        self.assertEqual(ledger_sync.calls, [])

    def test_warmup_refresh_error_emits_warn_event(self) -> None:
        ledger_sync = _LedgerSyncStub(fail_refresh=True)
        debug_hub = _DebugHubStub()
        service = MarketLedgerWarmupService(
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=True),
            debug_hub=debug_hub,
            ledger_sync_service=ledger_sync,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )

        self.assertEqual(ledger_sync.calls, [("binance:spot:ETH/USDT:1d", 160)])
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0].get("level"), "warn")
        self.assertIn("refresh_failed", (debug_hub.events[0].get("data") or {}).get("error", ""))

    def test_warmup_is_debounced_for_same_series_and_target(self) -> None:
        ledger_sync = _LedgerSyncStub()
        service = MarketLedgerWarmupService(
            runtime_flags=_RuntimeFlagsStub(enable_read_ledger_warmup=True, enable_debug_api=False),
            debug_hub=_DebugHubStub(),
            ledger_sync_service=ledger_sync,
            warmup_cooldown_seconds=60.0,
        )

        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )
        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=160,
        )
        service.ensure_ledgers_warm(
            series_id="binance:spot:ETH/USDT:1d",
            store_head_time=220,
        )

        self.assertEqual(
            ledger_sync.calls,
            [
                ("binance:spot:ETH/USDT:1d", 160),
                ("binance:spot:ETH/USDT:1d", 220),
            ],
        )


if __name__ == "__main__":
    unittest.main()
