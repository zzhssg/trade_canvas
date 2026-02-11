from __future__ import annotations

import unittest

from backend.app.market_data import CatchupReadResult, FreshnessSnapshot
from backend.app.market_query_service import MarketQueryService
from backend.app.schemas import CandleClosed


class _MarketDataStub:
    def __init__(self, *, candles: list[CandleClosed], head_time: int | None) -> None:
        self._candles = candles
        self._head_time = head_time
        self.read_calls: list[tuple[str, int | None, int]] = []
        self.freshness_calls: list[str] = []

    def read_candles(self, req) -> CatchupReadResult:
        self.read_calls.append((str(req.series_id), req.since, int(req.limit)))
        return CatchupReadResult(
            series_id=str(req.series_id),
            effective_since=req.since,
            candles=list(self._candles),
            gap_payload=None,
        )

    def freshness(self, *, series_id: str, now_time: int | None = None) -> FreshnessSnapshot:
        _ = now_time
        self.freshness_calls.append(str(series_id))
        return FreshnessSnapshot(
            series_id=str(series_id),
            head_time=None if self._head_time is None else int(self._head_time),
            now_time=0,
            lag_seconds=None,
            state="missing",
        )


class _BackfillStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int | None]] = []

    def ensure_tail_coverage(self, *, series_id: str, target_candles: int, to_time: int | None) -> int:
        self.calls.append((str(series_id), int(target_candles), None if to_time is None else int(to_time)))
        return int(target_candles)


class _RuntimeFlagsStub:
    def __init__(
        self,
        *,
        enable_market_auto_tail_backfill: bool,
        market_auto_tail_backfill_max_candles: int | None,
        enable_debug_api: bool,
    ) -> None:
        self.enable_market_auto_tail_backfill = bool(enable_market_auto_tail_backfill)
        self.market_auto_tail_backfill_max_candles = (
            None if market_auto_tail_backfill_max_candles is None else int(market_auto_tail_backfill_max_candles)
        )
        self.enable_debug_api = bool(enable_debug_api)


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


class MarketQueryServiceTests(unittest.TestCase):
    def test_get_candles_applies_auto_backfill_and_cap(self) -> None:
        market_data = _MarketDataStub(candles=[], head_time=None)
        backfill = _BackfillStub()
        flags = _RuntimeFlagsStub(
            enable_market_auto_tail_backfill=True,
            market_auto_tail_backfill_max_candles=3,
            enable_debug_api=False,
        )
        debug_hub = _DebugHubStub()
        service = MarketQueryService(
            market_data=market_data,
            backfill=backfill,
            runtime_flags=flags,
            debug_hub=debug_hub,
        )

        _ = service.get_candles(
            series_id="binance:futures:BTC/USDT:1m",
            since=None,
            limit=10,
        )
        self.assertEqual(backfill.calls, [("binance:futures:BTC/USDT:1m", 3, None)])

    def test_get_candles_emits_debug_event_when_enabled_and_non_empty(self) -> None:
        candles = [
            CandleClosed(candle_time=100, open=1.0, high=1.1, low=0.9, close=1.0, volume=10.0),
            CandleClosed(candle_time=160, open=1.1, high=1.2, low=1.0, close=1.1, volume=11.0),
        ]
        market_data = _MarketDataStub(candles=candles, head_time=160)
        backfill = _BackfillStub()
        flags = _RuntimeFlagsStub(
            enable_market_auto_tail_backfill=False,
            market_auto_tail_backfill_max_candles=None,
            enable_debug_api=True,
        )
        debug_hub = _DebugHubStub()
        service = MarketQueryService(
            market_data=market_data,
            backfill=backfill,
            runtime_flags=flags,
            debug_hub=debug_hub,
        )

        resp = service.get_candles(
            series_id="binance:futures:BTC/USDT:1m",
            since=100,
            limit=500,
        )
        self.assertEqual(resp.server_head_time, 160)
        self.assertEqual([int(item.candle_time) for item in resp.candles], [100, 160])
        self.assertEqual(market_data.read_calls, [("binance:futures:BTC/USDT:1m", 100, 500)])
        self.assertEqual(len(debug_hub.events), 1)
        self.assertEqual(debug_hub.events[0]["event"], "read.http.market_candles")

    def test_get_candles_is_pure_read_without_ledger_warmup_side_effect(self) -> None:
        candles = [CandleClosed(candle_time=160, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)]
        market_data = _MarketDataStub(candles=candles, head_time=160)
        backfill = _BackfillStub()
        flags = _RuntimeFlagsStub(
            enable_market_auto_tail_backfill=False,
            market_auto_tail_backfill_max_candles=None,
            enable_debug_api=True,
        )
        debug_hub = _DebugHubStub()
        service = MarketQueryService(
            market_data=market_data,
            backfill=backfill,
            runtime_flags=flags,
            debug_hub=debug_hub,
        )

        _ = service.get_candles(
            series_id="binance:spot:ETH/USDT:1d",
            since=None,
            limit=2000,
        )
        events = [str(item.get("event")) for item in debug_hub.events]
        self.assertEqual(events, ["read.http.market_candles"])
        self.assertNotIn("read.http.market_candles_ledger_warmup", events)


if __name__ == "__main__":
    unittest.main()
