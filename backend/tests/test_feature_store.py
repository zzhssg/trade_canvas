from __future__ import annotations

import tempfile
from pathlib import Path

from backend.app.feature.store import FeatureStore, FeatureVectorWrite


def test_feature_store_upsert_and_read_window() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = FeatureStore(db_path=Path(td) / "feature.db")

        with store.connect() as conn:
            changed = store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id="s1",
                        candle_time=100,
                        candle_id="s1:100",
                        values={"feature_event_count": 1.0, "pen_event_count": 1.0},
                    ),
                    FeatureVectorWrite(
                        series_id="s1",
                        candle_time=160,
                        candle_id="s1:160",
                        values={"feature_event_count": 2.0, "pen_event_count": 2.0},
                    ),
                ],
            )
            store.upsert_head_time_in_conn(conn, series_id="s1", head_time=160)
            conn.commit()

        assert changed == 2
        assert store.head_time("s1") == 160

        rows = store.get_rows_between_times(
            series_id="s1",
            start_candle_time=100,
            end_candle_time=200,
            limit=10,
        )
        assert [int(row.candle_time) for row in rows] == [100, 160]
        assert [float(row.values["feature_event_count"] or 0.0) for row in rows] == [1.0, 2.0]


def test_feature_store_upsert_is_idempotent_for_same_payload() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = FeatureStore(db_path=Path(td) / "feature.db")

        with store.connect() as conn:
            first = store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id="s1",
                        candle_time=100,
                        candle_id="s1:100",
                        values={"feature_event_count": 1.0},
                    )
                ],
            )
            second = store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id="s1",
                        candle_time=100,
                        candle_id="s1:100",
                        values={"feature_event_count": 1.0},
                    )
                ],
            )
            conn.commit()

        assert first == 1
        assert second == 0

        row = store.get_row_at_or_before(series_id="s1", candle_time=100)
        assert row is not None
        assert float(row.values["feature_event_count"] or 0.0) == 1.0


def test_feature_store_clear_series_removes_rows_and_head() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = FeatureStore(db_path=Path(td) / "feature.db")

        with store.connect() as conn:
            store.upsert_rows_in_conn(
                conn,
                rows=[
                    FeatureVectorWrite(
                        series_id="s1",
                        candle_time=100,
                        candle_id="s1:100",
                        values={"feature_event_count": 1.0},
                    ),
                    FeatureVectorWrite(
                        series_id="s2",
                        candle_time=120,
                        candle_id="s2:120",
                        values={"feature_event_count": 2.0},
                    ),
                ],
            )
            store.upsert_head_time_in_conn(conn, series_id="s1", head_time=100)
            store.upsert_head_time_in_conn(conn, series_id="s2", head_time=120)
            conn.commit()

        with store.connect() as conn:
            store.clear_series_in_conn(conn, series_id="s1")
            conn.commit()

        assert store.head_time("s1") is None
        assert store.head_time("s2") == 120
        assert store.get_rows_between_times(
            series_id="s1",
            start_candle_time=0,
            end_candle_time=200,
        ) == []
        remain = store.get_rows_between_times(
            series_id="s2",
            start_candle_time=0,
            end_candle_time=200,
        )
        assert len(remain) == 1
        assert remain[0].series_id == "s2"
