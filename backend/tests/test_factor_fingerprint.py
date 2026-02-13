from __future__ import annotations

from pathlib import Path

from backend.app.factor import orchestrator as orchestrator_module
from backend.app.factor.fingerprint import build_series_fingerprint
from backend.app.factor.orchestrator import FactorOrchestrator
from backend.app.factor.runtime_config import FactorSettings
from backend.app.factor.store import FactorStore
from backend.app.storage.candle_store import CandleStore


def _build_orchestrator(tmp_path: Path) -> FactorOrchestrator:
    db_path = tmp_path / "market.db"
    return FactorOrchestrator(
        candle_store=CandleStore(db_path),
        factor_store=FactorStore(db_path),
    )


def test_factor_fingerprint_is_stable_for_same_input(tmp_path, monkeypatch) -> None:
    orchestrator = _build_orchestrator(tmp_path=tmp_path)
    _ = monkeypatch
    settings = FactorSettings()

    fp1 = build_series_fingerprint(
        series_id="binance:futures:BTC/USDT:1m",
        settings=settings,
        graph=orchestrator._graph,
        registry=orchestrator._registry,
        orchestrator_file=Path(orchestrator_module.__file__),
        logic_version_override="",
    )
    fp2 = build_series_fingerprint(
        series_id="binance:futures:BTC/USDT:1m",
        settings=settings,
        graph=orchestrator._graph,
        registry=orchestrator._registry,
        orchestrator_file=Path(orchestrator_module.__file__),
        logic_version_override="",
    )
    assert fp1 == fp2


def test_factor_fingerprint_changes_when_logic_version_override_changes(tmp_path, monkeypatch) -> None:
    orchestrator = _build_orchestrator(tmp_path=tmp_path)
    _ = monkeypatch
    settings = FactorSettings()
    series_id = "binance:futures:BTC/USDT:1m"

    fp_v1 = build_series_fingerprint(
        series_id=series_id,
        settings=settings,
        graph=orchestrator._graph,
        registry=orchestrator._registry,
        orchestrator_file=Path(orchestrator_module.__file__),
        logic_version_override="v1",
    )

    fp_v2 = build_series_fingerprint(
        series_id=series_id,
        settings=settings,
        graph=orchestrator._graph,
        registry=orchestrator._registry,
        orchestrator_file=Path(orchestrator_module.__file__),
        logic_version_override="v2",
    )

    assert fp_v1 != fp_v2
