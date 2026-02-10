from __future__ import annotations

from pathlib import Path

from backend.app.factor_fingerprint_rebuild import FactorFingerprintRebuildCoordinator
from backend.app.factor_store import FactorEventWrite, FactorStore
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


class _DebugHubStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


def _seed_candles(store: CandleStore, *, series_id: str, candle_times: list[int] | tuple[int, ...] = (60, 120, 180)) -> None:
    for candle_time in candle_times:
        store.upsert_closed(
            series_id,
            CandleClosed(
                candle_time=int(candle_time),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            ),
        )


def _seed_factor_data(store: FactorStore, *, series_id: str, fingerprint: str) -> None:
    with store.connect() as conn:
        store.insert_events_in_conn(
            conn,
            events=[
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pivot",
                    candle_time=180,
                    kind="pivot.major",
                    event_key="seed",
                    payload={"pivot_time": 120, "visible_time": 180},
                )
            ],
        )
        store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=180)
        store.upsert_series_fingerprint_in_conn(conn, series_id=series_id, fingerprint=fingerprint)
        conn.commit()


def _new_stores(tmp_path: Path) -> tuple[CandleStore, FactorStore]:
    db_path = tmp_path / "market.db"
    return CandleStore(db_path), FactorStore(db_path)


def test_fingerprint_rebuild_forces_trim_clear_and_fingerprint_update(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "100")
    series_id = "binance:futures:BTC/USDT:1m"
    candle_store, factor_store = _new_stores(tmp_path=tmp_path)
    candle_times = [60 * (i + 1) for i in range(101)]
    _seed_candles(candle_store, series_id=series_id, candle_times=candle_times)
    _seed_factor_data(factor_store, series_id=series_id, fingerprint="old")
    debug_hub = _DebugHubStub()

    outcome = FactorFingerprintRebuildCoordinator(
        candle_store=candle_store,
        factor_store=factor_store,
        debug_hub=debug_hub,
    ).ensure_series_ready(
        series_id=series_id,
        auto_rebuild=True,
        current_fingerprint="new",
    )

    assert outcome.forced is True
    assert outcome.keep_candles == 100
    assert outcome.trimmed_rows == 1

    candles = candle_store.get_closed_between_times(
        series_id,
        start_time=0,
        end_time=999999,
        limit=200,
    )
    assert len(candles) == 100
    assert int(candles[0].candle_time) == int(candle_times[1])
    assert int(candles[-1].candle_time) == int(candle_times[-1])
    assert factor_store.head_time(series_id) is None
    assert factor_store.get_events_between_times(
        series_id=series_id,
        factor_name=None,
        start_candle_time=0,
        end_candle_time=9999,
        limit=10,
    ) == []
    fp = factor_store.get_series_fingerprint(series_id)
    assert fp is not None
    assert fp.fingerprint == "new"
    assert len(debug_hub.events) == 1
    assert debug_hub.events[0].get("event") == "factor.fingerprint.rebuild"


def test_fingerprint_rebuild_noop_when_fingerprint_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "1")
    series_id = "binance:futures:BTC/USDT:1m"
    candle_store, factor_store = _new_stores(tmp_path=tmp_path)
    _seed_candles(candle_store, series_id=series_id)
    _seed_factor_data(factor_store, series_id=series_id, fingerprint="same")
    debug_hub = _DebugHubStub()

    outcome = FactorFingerprintRebuildCoordinator(
        candle_store=candle_store,
        factor_store=factor_store,
        debug_hub=debug_hub,
    ).ensure_series_ready(
        series_id=series_id,
        auto_rebuild=True,
        current_fingerprint="same",
    )

    assert outcome.forced is False
    candles = candle_store.get_closed_between_times(
        series_id,
        start_time=0,
        end_time=9999,
        limit=10,
    )
    assert len(candles) == 3
    assert factor_store.head_time(series_id) == 180
    assert len(
        factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=0,
            end_candle_time=9999,
            limit=10,
        )
    ) == 1
    assert len(debug_hub.events) == 0


def test_fingerprint_rebuild_noop_when_auto_rebuild_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_FACTOR_REBUILD_KEEP_CANDLES", "1")
    series_id = "binance:futures:BTC/USDT:1m"
    candle_store, factor_store = _new_stores(tmp_path=tmp_path)
    _seed_candles(candle_store, series_id=series_id)
    _seed_factor_data(factor_store, series_id=series_id, fingerprint="old")

    outcome = FactorFingerprintRebuildCoordinator(
        candle_store=candle_store,
        factor_store=factor_store,
    ).ensure_series_ready(
        series_id=series_id,
        auto_rebuild=False,
        current_fingerprint="new",
    )

    assert outcome.forced is False
    candles = candle_store.get_closed_between_times(
        series_id,
        start_time=0,
        end_time=9999,
        limit=10,
    )
    assert len(candles) == 3
    fp = factor_store.get_series_fingerprint(series_id)
    assert fp is not None
    assert fp.fingerprint == "old"
