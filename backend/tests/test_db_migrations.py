from __future__ import annotations

from backend.app.factor.store import FactorEventWrite, FactorStore
from backend.app.overlay.store import OverlayStore
from backend.app.schemas import CandleClosed
from backend.app.store import CandleStore


def test_local_store_instances_share_state_when_db_path_is_same(tmp_path) -> None:
    db_path = tmp_path / "market.db"
    series_id = "binance:futures:BTC/USDT:1m"

    candle_store_a = CandleStore(db_path=db_path)
    candle_store_b = CandleStore(db_path=db_path)
    candle_store_a.upsert_closed(
        series_id,
        CandleClosed(candle_time=60, open=1, high=1, low=1, close=1, volume=1),
    )
    assert candle_store_b.head_time(series_id) == 60

    factor_store_a = FactorStore(db_path=db_path)
    factor_store_b = FactorStore(db_path=db_path)
    with factor_store_a.connect() as conn:
        factor_store_a.insert_events_in_conn(
            conn,
            events=[
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pivot",
                    candle_time=60,
                    kind="pivot.major",
                    event_key="pivot:60",
                    payload={"pivot_time": 60},
                )
            ],
        )
        conn.commit()
    assert factor_store_b.last_event_id(series_id) == 1

    overlay_store_a = OverlayStore(db_path=db_path)
    overlay_store_b = OverlayStore(db_path=db_path)
    with overlay_store_a.connect() as conn:
        overlay_store_a.insert_instruction_version_in_conn(
            conn,
            series_id=series_id,
            instruction_id="pivot.major:60",
            kind="marker",
            visible_time=60,
            payload={"time": 60},
        )
        conn.commit()
    assert overlay_store_b.last_version_id(series_id) == 1


def test_local_store_instances_are_isolated_between_db_paths(tmp_path) -> None:
    db_path_a = tmp_path / "a.db"
    db_path_b = tmp_path / "b.db"
    series_id = "binance:futures:BTC/USDT:1m"

    store_a = CandleStore(db_path=db_path_a)
    store_b = CandleStore(db_path=db_path_b)
    store_a.upsert_closed(
        series_id,
        CandleClosed(candle_time=120, open=2, high=2, low=2, close=2, volume=2),
    )

    assert store_a.head_time(series_id) == 120
    assert store_b.head_time(series_id) is None

