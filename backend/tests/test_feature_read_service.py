from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.app.core.schemas import CandleClosed
from backend.app.core.service_errors import ServiceError
from backend.app.feature.read_service import FeatureReadService
from backend.app.feature.store import FeatureStore, FeatureVectorWrite
from backend.app.storage.candle_store import CandleStore


def _candle(candle_time: int, close: float = 1.0) -> CandleClosed:
    return CandleClosed(
        candle_time=int(candle_time),
        open=float(close),
        high=float(close),
        low=float(close),
        close=float(close),
        volume=1.0,
    )


def _seed_candles(*, store: CandleStore, series_id: str) -> None:
    with store.connect() as conn:
        store.upsert_many_closed_in_conn(
            conn,
            series_id,
            [_candle(100, 1.0), _candle(160, 2.0)],
        )
        conn.commit()


def test_feature_read_service_strict_mode_rejects_stale_feature_head() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_read.db"
        series_id = "binance:futures:BTC/USDT:1m"
        candle_store = CandleStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        _seed_candles(store=candle_store, series_id=series_id)

        with feature_store.connect() as conn:
            feature_store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id=series_id,
                        candle_time=100,
                        candle_id=f"{series_id}:100",
                        values={"feature_event_count": 1.0},
                    )
                ],
            )
            feature_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=100)
            conn.commit()

        service = FeatureReadService(store=candle_store, feature_store=feature_store, strict_mode=True)

        with pytest.raises(ServiceError, match=r"feature_read\.ledger_out_of_sync"):
            service.read_batch(series_id=series_id, at_time=160, window_candles=20)


def test_feature_read_service_returns_normalized_feature_batch() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_read.db"
        series_id = "binance:futures:BTC/USDT:1m"
        candle_store = CandleStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        _seed_candles(store=candle_store, series_id=series_id)

        with feature_store.connect() as conn:
            feature_store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id=series_id,
                        candle_time=100,
                        candle_id=f"{series_id}:100",
                        values={"feature_event_count": 1.0},
                    ),
                    FeatureVectorWrite(
                        series_id=series_id,
                        candle_time=160,
                        candle_id=f"{series_id}:160",
                        values={"feature_event_count": 2.0, "pen_event_count": 2.0},
                    ),
                ],
            )
            feature_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=160)
            conn.commit()

        service = FeatureReadService(store=candle_store, feature_store=feature_store, strict_mode=True)
        batch = service.read_batch(series_id=series_id, at_time=160, window_candles=20)

        assert batch.aligned_time == 160
        assert [column.key for column in batch.columns] == ["feature_event_count", "pen_event_count"]
        assert [row.candle_time for row in batch.rows] == [100, 160]
        assert batch.rows[0].values["pen_event_count"] is None
        assert float(batch.rows[1].values["pen_event_count"] or 0.0) == 2.0


def test_feature_read_service_can_skip_strict_freshness_check() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_read.db"
        series_id = "binance:futures:BTC/USDT:1m"
        candle_store = CandleStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        _seed_candles(store=candle_store, series_id=series_id)

        with feature_store.connect() as conn:
            feature_store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id=series_id,
                        candle_time=100,
                        candle_id=f"{series_id}:100",
                        values={"feature_event_count": 1.0},
                    )
                ],
            )
            feature_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=100)
            conn.commit()

        service = FeatureReadService(store=candle_store, feature_store=feature_store, strict_mode=True)
        batch = service.read_batch(
            series_id=series_id,
            at_time=160,
            window_candles=20,
            ensure_fresh=False,
        )

        assert batch.aligned_time == 160
        assert [row.candle_time for row in batch.rows] == [100]
