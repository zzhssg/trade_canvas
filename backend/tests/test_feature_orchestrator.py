from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.app.factor.capability_manifest import FactorCapabilitySpec
from backend.app.factor.store import FactorEventWrite, FactorStore
from backend.app.feature.orchestrator import FeatureOrchestrator, FeatureSettings
from backend.app.feature.store import FeatureStore


def _insert_factor_events(*, factor_store: FactorStore, series_id: str) -> None:
    with factor_store.connect() as conn:
        factor_store.insert_events_in_conn(
            conn,
            events=[
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pen",
                    candle_time=100,
                    kind="pen.confirmed",
                    event_key="pen:100:0",
                    payload={"i": 0, "direction": 1},
                ),
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pivot",
                    candle_time=100,
                    kind="pivot.major",
                    event_key="pivot:100:0",
                    payload={"i": 0},
                ),
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pen",
                    candle_time=160,
                    kind="pen.confirmed",
                    event_key="pen:160:0",
                    payload={"i": 1, "direction": -1},
                ),
                FactorEventWrite(
                    series_id=series_id,
                    factor_name="pen",
                    candle_time=160,
                    kind="pen.confirmed",
                    event_key="pen:160:1",
                    payload={"i": 2, "direction": 1},
                ),
            ],
        )
        factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=160)
        conn.commit()


def test_feature_orchestrator_uses_capability_manifest_to_filter_factors() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_orch.db"
        factor_store = FactorStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        series_id = "binance:futures:BTC/USDT:1m"
        _insert_factor_events(factor_store=factor_store, series_id=series_id)

        orchestrator = FeatureOrchestrator(
            factor_store=factor_store,
            feature_store=feature_store,
            capability_overrides={
                "pen": FactorCapabilitySpec(factor_name="pen", enable_feature=True),
            },
        )

        result = orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=160)

        assert result.wrote == 2
        assert result.head_time == 160
        assert feature_store.head_time(series_id) == 160

        rows = feature_store.get_rows_between_times(
            series_id=series_id,
            start_candle_time=0,
            end_candle_time=200,
        )
        assert [int(row.candle_time) for row in rows] == [100, 160]
        row_100, row_160 = rows
        assert float(row_100.values["feature_event_count"] or 0.0) == 1.0
        assert float(row_100.values["pen_event_count"] or 0.0) == 1.0
        assert float(row_100.values["pen_confirmed_count"] or 0.0) == 1.0
        assert int(row_100.values["pen_confirmed_direction"] or 0) == 1
        assert "pivot_event_count" not in row_100.values
        assert float(row_160.values["feature_event_count"] or 0.0) == 2.0
        assert float(row_160.values["pen_event_count"] or 0.0) == 2.0
        assert float(row_160.values["pen_confirmed_count"] or 0.0) == 2.0
        assert int(row_160.values["pen_confirmed_direction"] or 0) == 1


def test_feature_orchestrator_rejects_when_factor_head_is_stale() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_orch.db"
        factor_store = FactorStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        series_id = "binance:futures:BTC/USDT:1m"

        with factor_store.connect() as conn:
            factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=100)
            conn.commit()

        orchestrator = FeatureOrchestrator(
            factor_store=factor_store,
            feature_store=feature_store,
            capability_overrides={
                "pen": FactorCapabilitySpec(factor_name="pen", enable_feature=True),
            },
        )

        with pytest.raises(RuntimeError, match="feature_factor_out_of_sync"):
            orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=160)


def test_feature_orchestrator_can_be_disabled_by_settings() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "feature_orch.db"
        factor_store = FactorStore(db_path=db_path)
        feature_store = FeatureStore(db_path=db_path)
        series_id = "binance:futures:BTC/USDT:1m"
        _insert_factor_events(factor_store=factor_store, series_id=series_id)

        orchestrator = FeatureOrchestrator(
            factor_store=factor_store,
            feature_store=feature_store,
            capability_overrides={
                "pen": FactorCapabilitySpec(factor_name="pen", enable_feature=True),
            },
            settings=FeatureSettings(ingest_enabled=False),
        )

        result = orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=160)
        assert result.wrote == 0
        assert result.head_time is None
        assert feature_store.head_time(series_id) is None
