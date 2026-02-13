from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from backend.app.market_data import (
    BackfillGapRequest,
    CatchupReadRequest,
    DefaultMarketDataOrchestrator,
    StoreBackfillService,
    StoreCandleReadService,
    StoreFreshnessService,
    WsMessageParser,
    WsSubscriptionCoordinator,
    WsSubscribeRequest,
    build_derived_initial_backfill_handler,
    build_gap_backfill_handler,
    build_ws_error_payload,
)
from backend.app.runtime_metrics import RuntimeMetrics
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


def _upsert_times(store: CandleStore, *, series_id: str, times: list[int]) -> None:
    for t in times:
        store.upsert_closed(
            series_id,
            CandleClosed(candle_time=t, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
        )


def test_store_candle_read_service_tail_and_incremental() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:BTC/USDT:1m"
        _upsert_times(store, series_id=series_id, times=[100, 160, 220])

        svc = StoreCandleReadService(store=store)
        tail = svc.read_tail(series_id=series_id, limit=2)
        assert [int(c.candle_time) for c in tail] == [160, 220]

        inc = svc.read_incremental(series_id=series_id, since=160, limit=10)
        assert [int(c.candle_time) for c in inc] == [220]

        between = svc.read_between(series_id=series_id, start_time=100, end_time=160, limit=10)
        assert [int(c.candle_time) for c in between] == [100, 160]


def test_store_freshness_service_classifies_state_and_handles_unknown_series_format() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:BTC/USDT:1m"
        _upsert_times(store, series_id=series_id, times=[100])

        freshness = StoreFreshnessService(
            store=store,
            fresh_window_candles=2,
            stale_window_candles=5,
            now_fn=lambda: 0,
        )
        missing = freshness.snapshot(series_id="binance:futures:ETH/USDT:1m", now_time=200)
        assert missing.state == "missing"
        assert missing.lag_seconds is None

        fresh = freshness.snapshot(series_id=series_id, now_time=220)
        assert fresh.state == "fresh"
        assert fresh.lag_seconds == 120

        stale = freshness.snapshot(series_id=series_id, now_time=340)
        assert stale.state == "stale"
        assert stale.lag_seconds == 240

        degraded = freshness.snapshot(series_id=series_id, now_time=500)
        assert degraded.state == "degraded"
        assert degraded.lag_seconds == 400

        odd_series = "legacy_series_without_timeframe"
        _upsert_times(store, series_id=odd_series, times=[100])
        odd = freshness.snapshot(series_id=odd_series, now_time=200)
        assert odd.state == "degraded"
        assert odd.head_time == 100


def test_default_market_data_orchestrator_routes_read_and_ws_gap_heal() -> None:
    class _FakeWsDelivery:
        async def heal_catchup_gap(self, *, series_id: str, effective_since: int | None, catchup: list[CandleClosed]):
            return catchup, {"type": "gap", "series_id": series_id, "effective_since": effective_since}

    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:BTC/USDT:1m"
        _upsert_times(store, series_id=series_id, times=[100, 160, 220])

        orchestrator = DefaultMarketDataOrchestrator(
            reader=StoreCandleReadService(store=store),
            freshness=StoreFreshnessService(store=store),
            ws_delivery=_FakeWsDelivery(),
        )

        read = orchestrator.read_candles(CatchupReadRequest(series_id=series_id, since=100, limit=10))
        assert read.effective_since == 100
        assert [int(c.candle_time) for c in read.candles] == [160, 220]

        stream_out = asyncio.run(
            orchestrator.build_ws_subscribe(
                WsSubscribeRequest(
                    series_id=series_id,
                    since=100,
                    supports_batch=False,
                    limit=10,
                    get_last_sent=lambda: asyncio.sleep(0, result=160),
                )
            )
        )
        assert stream_out.effective_since == 160
        assert stream_out.read_count == 2
        assert stream_out.catchup_count == 1
        assert stream_out.gap_emitted is True
        assert [p["type"] for p in stream_out.payloads] == ["gap", "candle_closed"]
        assert stream_out.last_sent_time == 220

        batch_out = asyncio.run(
            orchestrator.build_ws_subscribe(
                WsSubscribeRequest(
                    series_id=series_id,
                    since=100,
                    supports_batch=True,
                    limit=10,
                    get_last_sent=lambda: asyncio.sleep(0, result=160),
                )
            )
        )
        assert batch_out.effective_since == 160
        assert batch_out.read_count == 2
        assert batch_out.catchup_count == 1
        assert batch_out.gap_emitted is True
        assert [p["type"] for p in batch_out.payloads] == ["gap", "candles_batch"]
        assert batch_out.last_sent_time == 220


def test_store_backfill_service_wraps_gap_and_tail_backfill() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:BTC/USDT:1m"

        def fake_gap_backfill(*, store: CandleStore, series_id: str, expected_next_time: int, actual_time: int) -> int:
            assert expected_next_time == 160
            assert actual_time == 220
            with store.connect() as conn:
                store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=160, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                conn.commit()
            return 1

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            assert limit in {2, 100}
            with store.connect() as conn:
                store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=220, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                conn.commit()
            return 3

        svc = StoreBackfillService(
            store=store,
            gap_backfill_fn=fake_gap_backfill,
            tail_backfill_fn=fake_tail_backfill,
        )

        gap_res = svc.backfill_gap(
            BackfillGapRequest(series_id=series_id, expected_next_time=160, actual_time=220)
        )
        assert gap_res.filled_count == 1
        assert store.head_time(series_id) == 160
        assert svc.ensure_tail_coverage(series_id=series_id, target_candles=100, to_time=None) == 3
        assert svc.ensure_tail_coverage(series_id=series_id, target_candles=2, to_time=220) == 2


def test_store_backfill_service_falls_back_to_ccxt_for_missing_window(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:SOL/USDT:1h"
        called: list[tuple[int, int]] = []

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            return 0

        def fake_ccxt_backfill(
            *,
            candle_store: CandleStore,
            series_id: str,
            start_time: int,
            end_time: int,
            batch_limit: int = 1000,
            ccxt_timeout_ms: int = 10_000,
        ) -> int:
            _ = batch_limit
            _ = ccxt_timeout_ms
            called.append((int(start_time), int(end_time)))
            with candle_store.connect() as conn:
                candle_store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=0, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                candle_store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=3600, open=2.0, high=3.0, low=1.5, close=2.5, volume=10.0),
                )
                conn.commit()
            return 2

        monkeypatch.setattr("backend.app.market_data.read_services.backfill_from_ccxt_range", fake_ccxt_backfill)

        svc = StoreBackfillService(
            store=store,
            tail_backfill_fn=fake_tail_backfill,
            enable_ccxt_backfill=True,
        )
        covered = svc.ensure_tail_coverage(series_id=series_id, target_candles=2, to_time=3600)
        assert covered == 2
        assert called == [(0, 3600)]


def test_store_backfill_service_to_time_none_uses_now_window_for_stale_series(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:SOL/USDT:1h"
        called: list[tuple[int, int]] = []

        store.upsert_closed(
            series_id,
            CandleClosed(candle_time=0, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
        )

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            return 0

        def fake_ccxt_backfill(
            *,
            candle_store: CandleStore,
            series_id: str,
            start_time: int,
            end_time: int,
            batch_limit: int = 1000,
            ccxt_timeout_ms: int = 10_000,
        ) -> int:
            _ = batch_limit
            _ = ccxt_timeout_ms
            called.append((int(start_time), int(end_time)))
            with candle_store.connect() as conn:
                candle_store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=3600, open=2.0, high=3.0, low=1.5, close=2.5, volume=10.0),
                )
                conn.commit()
            return 1

        monkeypatch.setattr("backend.app.market_data.read_services.backfill_from_ccxt_range", fake_ccxt_backfill)
        monkeypatch.setattr("backend.app.market_data.read_services.time.time", lambda: 3661)

        svc = StoreBackfillService(
            store=store,
            tail_backfill_fn=fake_tail_backfill,
            enable_ccxt_backfill=True,
            enable_ccxt_backfill_on_read=True,
        )
        covered = svc.ensure_tail_coverage(series_id=series_id, target_candles=2, to_time=None)
        assert covered == 2
        assert called == [(0, 3600)]


def test_store_backfill_service_to_time_none_skips_ccxt_by_default(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:SOL/USDT:1h"
        called: list[tuple[int, int]] = []

        store.upsert_closed(
            series_id,
            CandleClosed(candle_time=0, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
        )

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            return 0

        def fake_ccxt_backfill(
            *,
            candle_store: CandleStore,
            series_id: str,
            start_time: int,
            end_time: int,
            batch_limit: int = 1000,
            ccxt_timeout_ms: int = 10_000,
        ) -> int:
            _ = candle_store
            _ = batch_limit
            _ = ccxt_timeout_ms
            called.append((int(start_time), int(end_time)))
            return 0

        monkeypatch.setattr("backend.app.market_data.read_services.backfill_from_ccxt_range", fake_ccxt_backfill)
        monkeypatch.setattr("backend.app.market_data.read_services.time.time", lambda: 3661)

        svc = StoreBackfillService(
            store=store,
            tail_backfill_fn=fake_tail_backfill,
            enable_ccxt_backfill=True,
        )
        covered = svc.ensure_tail_coverage(series_id=series_id, target_candles=2, to_time=None)
        assert covered == 1
        assert called == []


def test_store_backfill_service_to_time_none_strict_closed_only_caps_at_previous_closed(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:SOL/USDT:1h"
        called: list[tuple[int, int]] = []

        store.upsert_closed(
            series_id,
            CandleClosed(candle_time=0, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
        )

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            return 0

        def fake_ccxt_backfill(
            *,
            candle_store: CandleStore,
            series_id: str,
            start_time: int,
            end_time: int,
            batch_limit: int = 1000,
            ccxt_timeout_ms: int = 10_000,
        ) -> int:
            _ = batch_limit
            _ = ccxt_timeout_ms
            called.append((int(start_time), int(end_time)))
            with candle_store.connect() as conn:
                candle_store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=3600, open=2.0, high=3.0, low=1.5, close=2.5, volume=10.0),
                )
                conn.commit()
            return 1

        monkeypatch.setattr("backend.app.market_data.read_services.backfill_from_ccxt_range", fake_ccxt_backfill)
        monkeypatch.setattr("backend.app.market_data.read_services.time.time", lambda: 7201)

        svc = StoreBackfillService(
            store=store,
            tail_backfill_fn=fake_tail_backfill,
            enable_ccxt_backfill=True,
            enable_ccxt_backfill_on_read=True,
            enable_strict_closed_only=True,
        )
        covered = svc.ensure_tail_coverage(series_id=series_id, target_candles=2, to_time=None)
        assert covered == 2
        assert called == [(0, 3600)]


def test_store_backfill_service_derived_5m_can_rollup_from_base_1m() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        base_series_id = "binance:futures:BTC/USDT:1m"
        derived_series_id = "binance:futures:BTC/USDT:5m"

        for t in range(3600, 4200, 60):
            store.upsert_closed(
                base_series_id,
                CandleClosed(candle_time=t, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
            )

        def fake_tail_backfill(store: CandleStore, *, series_id: str, limit: int) -> int:
            return 0

        svc = StoreBackfillService(
            store=store,
            tail_backfill_fn=fake_tail_backfill,
        )

        covered = svc.ensure_tail_coverage(series_id=derived_series_id, target_candles=3, to_time=4200)
        assert covered == 2
        assert store.head_time(derived_series_id) == 3900
        candles = store.get_closed(derived_series_id, since=None, limit=10)
        assert [int(c.candle_time) for c in candles] == [3600, 3900]


def test_build_gap_backfill_handler_applies_flag_and_reads_recovered_interval() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        series_id = "binance:futures:BTC/USDT:1m"
        _upsert_times(store, series_id=series_id, times=[220])

        def fake_gap_backfill(*, store: CandleStore, series_id: str, expected_next_time: int, actual_time: int) -> int:
            with store.connect() as conn:
                store.upsert_closed_in_conn(
                    conn,
                    series_id,
                    CandleClosed(candle_time=160, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
                )
                conn.commit()
            return 1

        reader = StoreCandleReadService(store=store)
        backfill = StoreBackfillService(
            store=store,
            gap_backfill_fn=fake_gap_backfill,
        )
        handler_disabled = build_gap_backfill_handler(
            reader=reader,
            backfill=backfill,
            enabled=False,
        )
        disabled = asyncio.run(handler_disabled(series_id, 160, 220))
        assert disabled == []

        handler_enabled = build_gap_backfill_handler(
            reader=reader,
            backfill=backfill,
            enabled=True,
        )
        recovered = asyncio.run(handler_enabled(series_id, 160, 220))
        assert [int(c.candle_time) for c in recovered] == [160]


def test_build_derived_initial_backfill_handler_bootstraps_and_updates_sidecars() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        base_series_id = "binance:futures:BTC/USDT:1m"
        derived_series_id = "binance:futures:BTC/USDT:5m"
        _upsert_times(store, series_id=base_series_id, times=[0, 60, 120, 180, 240])

        class _Factor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            def ingest_closed(self, *, series_id: str, up_to_candle_time: int):
                self.calls.append((series_id, int(up_to_candle_time)))
                return SimpleNamespace(rebuilt=True)

        class _Overlay:
            def __init__(self) -> None:
                self.reset_calls: list[str] = []
                self.ingest_calls: list[tuple[str, int]] = []

            def reset_series(self, *, series_id: str) -> None:
                self.reset_calls.append(series_id)

            def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
                self.ingest_calls.append((series_id, int(up_to_candle_time)))

        factor = _Factor()
        overlay = _Overlay()
        handler = build_derived_initial_backfill_handler(
            store=store,
            factor_orchestrator=factor,
            overlay_orchestrator=overlay,
            derived_enabled=True,
            derived_base_timeframe="1m",
            derived_timeframes=("5m",),
            derived_backfill_base_candles=2000,
        )

        asyncio.run(handler(series_id=derived_series_id))
        assert store.head_time(derived_series_id) == 0
        assert factor.calls == [(derived_series_id, 0)]
        assert overlay.reset_calls == [derived_series_id]
        assert overlay.ingest_calls == [(derived_series_id, 0)]

        asyncio.run(handler(series_id=derived_series_id))
        assert factor.calls == [(derived_series_id, 0)]
        assert overlay.ingest_calls == [(derived_series_id, 0)]


def test_build_derived_initial_backfill_handler_respects_disable_flag() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CandleStore(db_path=Path(td) / "market.db")
        base_series_id = "binance:futures:BTC/USDT:1m"
        derived_series_id = "binance:futures:BTC/USDT:5m"
        _upsert_times(store, series_id=base_series_id, times=[0, 60, 120, 180, 240])

        class _Noop:
            def ingest_closed(self, **kwargs):
                raise AssertionError("should not be called when derived is disabled")

            def reset_series(self, **kwargs):
                raise AssertionError("should not be called when derived is disabled")

        handler = build_derived_initial_backfill_handler(
            store=store,
            factor_orchestrator=_Noop(),
            overlay_orchestrator=_Noop(),
            derived_enabled=False,
            derived_base_timeframe="1m",
            derived_timeframes=("5m",),
            derived_backfill_base_candles=2000,
        )
        asyncio.run(handler(series_id=derived_series_id))
        assert store.head_time(derived_series_id) is None


def test_ws_subscription_coordinator_handles_capacity_and_calls_hub() -> None:
    class _Hub:
        def __init__(self) -> None:
            self.sub_calls: list[tuple[str, int | None, bool]] = []
            self.unsub_calls: list[str] = []
            self.pop_result: list[str] = []
            self.pop_calls = 0
            self.last_sent_time: int | None = None
            self.last_sent_series: str | None = None

        async def subscribe(self, ws, *, series_id: str, since: int | None, supports_batch: bool = False) -> None:
            self.sub_calls.append((series_id, since, bool(supports_batch)))

        async def unsubscribe(self, ws, *, series_id: str) -> None:
            self.unsub_calls.append(series_id)

        async def pop_ws(self, ws) -> list[str]:
            self.pop_calls += 1
            return list(self.pop_result)

        async def get_last_sent(self, ws, *, series_id: str) -> int | None:
            return None

        async def set_last_sent(self, ws, *, series_id: str, candle_time: int) -> None:
            self.last_sent_series = series_id
            self.last_sent_time = int(candle_time)

    class _OnDemand:
        def __init__(self) -> None:
            self.subscribed: list[str] = []
            self.unsubscribed: list[str] = []
            self.ok = True

        async def subscribe(self, series_id: str) -> bool:
            self.subscribed.append(series_id)
            return bool(self.ok)

        async def unsubscribe(self, series_id: str) -> None:
            self.unsubscribed.append(series_id)

    class _MarketData:
        async def build_ws_subscribe(self, req: WsSubscribeRequest):
            c = CandleClosed(candle_time=160, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
            payloads = [{"type": "candle_closed", "series_id": req.series_id, "candle": c.model_dump()}]
            return SimpleNamespace(
                series_id=req.series_id,
                effective_since=req.since,
                read_count=1,
                catchup_count=1,
                payloads=payloads,
                last_sent_time=160,
                gap_emitted=False,
            )

    hub = cast(Any, _Hub())
    ondemand = _OnDemand()
    metrics = RuntimeMetrics(enabled=True)
    svc = WsSubscriptionCoordinator(
        hub=hub,
        ondemand_subscribe=ondemand.subscribe,
        ondemand_unsubscribe=ondemand.unsubscribe,
        runtime_metrics=metrics,
    )
    ws = cast(Any, object())

    err = asyncio.run(
        svc.subscribe(
            ws=ws,
            series_id="binance:futures:BTC/USDT:1m",
            since=100,
            supports_batch=True,
            ondemand_enabled=True,
        )
    )
    assert err is None
    assert ondemand.subscribed == ["binance:futures:BTC/USDT:1m"]
    assert hub.sub_calls == [("binance:futures:BTC/USDT:1m", 100, True)]
    assert hub.last_sent_time is None

    err_dup = asyncio.run(
        svc.subscribe(
            ws=ws,
            series_id="binance:futures:BTC/USDT:1m",
            since=120,
            supports_batch=False,
            ondemand_enabled=True,
        )
    )
    assert err_dup is None
    assert ondemand.subscribed == ["binance:futures:BTC/USDT:1m"]
    assert hub.sub_calls == [
        ("binance:futures:BTC/USDT:1m", 100, True),
        ("binance:futures:BTC/USDT:1m", 120, False),
    ]

    async def _noop_backfill(*, series_id: str) -> None:
        return None

    err_flow, payloads = asyncio.run(
        svc.handle_subscribe(
            ws=ws,
            series_id="binance:futures:BTC/USDT:1m",
            since=100,
            supports_batch=False,
            ondemand_enabled=False,
            market_data=cast(Any, _MarketData()),
            derived_initial_backfill=_noop_backfill,
        )
    )
    assert err_flow is None
    assert [p["type"] for p in payloads] == ["candle_closed"]
    assert hub.last_sent_series == "binance:futures:BTC/USDT:1m"
    assert hub.last_sent_time == 160
    assert hub.sub_calls == [
        ("binance:futures:BTC/USDT:1m", 100, True),
        ("binance:futures:BTC/USDT:1m", 120, False),
        ("binance:futures:BTC/USDT:1m", 100, False),
    ]

    err_ok2 = asyncio.run(
        svc.subscribe(
            ws=ws,
            series_id="binance:futures:SOL/USDT:1m",
            since=100,
            supports_batch=False,
            ondemand_enabled=True,
        )
    )
    assert err_ok2 is None
    assert hub.sub_calls == [
        ("binance:futures:BTC/USDT:1m", 100, True),
        ("binance:futures:BTC/USDT:1m", 120, False),
        ("binance:futures:BTC/USDT:1m", 100, False),
        ("binance:futures:SOL/USDT:1m", 100, False),
    ]

    ondemand.ok = False
    err2 = asyncio.run(
        svc.subscribe(
            ws=ws,
            series_id="binance:futures:ETH/USDT:1m",
            since=100,
            supports_batch=False,
            ondemand_enabled=True,
        )
    )
    assert err2 is not None
    assert err2["code"] == "capacity"
    assert hub.sub_calls == [
        ("binance:futures:BTC/USDT:1m", 100, True),
        ("binance:futures:BTC/USDT:1m", 120, False),
        ("binance:futures:BTC/USDT:1m", 100, False),
        ("binance:futures:SOL/USDT:1m", 100, False),
    ]

    asyncio.run(
        svc.unsubscribe(
            ws=ws,
            series_id="binance:futures:BTC/USDT:1m",
            ondemand_enabled=True,
        )
    )
    assert ondemand.unsubscribed == ["binance:futures:BTC/USDT:1m"]
    assert hub.unsub_calls == ["binance:futures:BTC/USDT:1m"]

    asyncio.run(
        svc.unsubscribe(
            ws=ws,
            series_id="binance:futures:BTC/USDT:1m",
            ondemand_enabled=True,
        )
    )
    assert ondemand.unsubscribed == ["binance:futures:BTC/USDT:1m"]
    assert hub.unsub_calls == ["binance:futures:BTC/USDT:1m", "binance:futures:BTC/USDT:1m"]

    hub.pop_result = ["binance:futures:SOL/USDT:1m", "binance:futures:DOGE/USDT:1m"]
    asyncio.run(
        svc.cleanup_disconnect(
            ws=ws,
            ondemand_enabled=True,
        )
    )
    assert hub.pop_calls == 1
    assert set(ondemand.unsubscribed) == {
        "binance:futures:BTC/USDT:1m",
        "binance:futures:SOL/USDT:1m",
        "binance:futures:DOGE/USDT:1m",
    }
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["market_ws_subscribe_total{result=ok}"] == 4.0
    assert snapshot["counters"]["market_ws_subscribe_total{result=capacity}"] == 1.0
    assert snapshot["counters"]["market_ws_unsubscribe_total{result=ok}"] == 1.0
    assert snapshot["counters"]["market_ws_unsubscribe_total{result=noop}"] == 1.0
    assert snapshot["counters"]["market_ws_payloads_total"] == 1.0
    assert snapshot["counters"]["market_ws_catchup_candles_total"] == 1.0
    assert snapshot["counters"]["market_ws_disconnect_cleanup_total"] == 1.0
    assert snapshot["counters"]["market_ws_disconnect_unsubscribe_total{result=ok}"] == 2.0
    assert snapshot["gauges"]["market_ws_last_catchup_count"] == 1.0
    assert snapshot["gauges"]["market_ws_last_payload_count"] == 1.0
    assert snapshot["gauges"]["market_ws_disconnect_cleanup_series_count"] == 2.0
    assert snapshot["gauges"]["market_ws_active_subscriptions"] == 0.0
    assert snapshot["timers"]["market_ws_subscribe_duration_ms{result=ok}"]["count"] == 4.0
    assert snapshot["timers"]["market_ws_subscribe_duration_ms{result=capacity}"]["count"] == 1.0
    assert snapshot["timers"]["market_ws_unsubscribe_duration_ms{result=ok}"]["count"] == 1.0
    assert snapshot["timers"]["market_ws_unsubscribe_duration_ms{result=noop}"]["count"] == 1.0


def test_ws_message_parser_validates_subscribe_and_unsubscribe_payloads() -> None:
    parser = WsMessageParser()

    assert parser.parse_message_type({"type": "subscribe"}) == "subscribe"

    try:
        parser.parse_message_type(["bad"])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "invalid message envelope"

    try:
        parser.parse_message_type({"series_id": "binance:futures:BTC/USDT:1m"})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "missing message type"

    cmd = parser.parse_subscribe({"type": "subscribe", "series_id": "binance:futures:BTC/USDT:1m", "since": 100})
    assert cmd.series_id == "binance:futures:BTC/USDT:1m"
    assert cmd.since == 100
    assert cmd.supports_batch is False

    for payload, expected in [
        ({"type": "subscribe"}, "missing series_id"),
        ({"type": "subscribe", "series_id": "binance:futures:BTC/USDT:1m", "since": "100"}, "invalid since"),
        ({"type": "subscribe", "series_id": "binance:futures:BTC/USDT:1m", "supports_batch": "1"}, "invalid supports_batch"),
    ]:
        try:
            parser.parse_subscribe(payload)
            assert False, "expected ValueError"
        except ValueError as exc:
            assert str(exc) == expected

    assert parser.parse_unsubscribe_series_id({"type": "unsubscribe", "series_id": "binance:futures:ETH/USDT:1m"}) == (
        "binance:futures:ETH/USDT:1m"
    )
    assert parser.parse_unsubscribe_series_id({"type": "unsubscribe"}) is None

    assert parser.unknown_message_type(msg_type="noop") == {
        "type": "error",
        "code": "bad_request",
        "message": "unknown message type: noop",
    }


def test_build_ws_error_payload_supports_optional_series_id() -> None:
    assert build_ws_error_payload(code="bad_request", message="missing message type") == {
        "type": "error",
        "code": "bad_request",
        "message": "missing message type",
    }
    assert build_ws_error_payload(code="capacity", message="ondemand_ingest_capacity", series_id="s1") == {
        "type": "error",
        "code": "capacity",
        "message": "ondemand_ingest_capacity",
        "series_id": "s1",
    }
