from __future__ import annotations

import json
from pathlib import Path

from trade_oracle.config import OracleSettings
from trade_oracle.models import Candle
from trade_oracle.service import OracleService


def _load_mock_candles() -> list[Candle]:
    path = Path("trade_oracle/fixtures/btc_1d_mock_120.json")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [Candle(**r) for r in rows]


class _FakeMarket:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def fetch_candles(self, **kwargs) -> list[Candle]:
        return self._candles


def test_analyze_current_builds_report():
    settings = OracleSettings(
        market_api_base="http://127.0.0.1:9999",
        enable_sx_crosscheck=False,
        enable_strategy_search=False,
        enable_backtest=True,
        market_limit=120,
        wf_train_size=60,
        wf_test_size=20,
        trade_fee_rate=0.0008,
        target_win_rate=0.5,
        target_reward_risk=2.0,
        enable_true_solar_time=True,
        solar_longitude_deg=24.9384,
        solar_tz_offset_hours=2.0,
        strict_calendar_lib=False,
    )
    svc = OracleService(settings)

    mock_candles = _load_mock_candles()
    svc.market = _FakeMarket(mock_candles)

    payload, report = svc.analyze_current(series_id="binance:futures:BTC/USDT:1d", symbol="BTC")

    assert payload["series_id"] == "binance:futures:BTC/USDT:1d"
    assert payload["bias"] in {"bullish", "bearish", "neutral"}
    assert "factor_scores" in payload and len(payload["factor_scores"]) == 3
    assert "BTC 八字走势分析报告" in report
    assert payload["evidence"]["candles"]["count"] == 120


def test_analyze_current_without_backtest():
    settings = OracleSettings(
        market_api_base="http://127.0.0.1:9999",
        enable_sx_crosscheck=True,
        enable_strategy_search=False,
        enable_backtest=False,
        market_limit=120,
        wf_train_size=60,
        wf_test_size=20,
        trade_fee_rate=0.0008,
        target_win_rate=0.5,
        target_reward_risk=2.0,
        enable_true_solar_time=True,
        solar_longitude_deg=24.9384,
        solar_tz_offset_hours=2.0,
        strict_calendar_lib=False,
    )
    svc = OracleService(settings)
    mock_candles = _load_mock_candles()
    svc.market = _FakeMarket(mock_candles)

    payload, _ = svc.analyze_current(series_id="binance:futures:BTC/USDT:1d", symbol="BTC")

    assert payload["strategy_metrics"] is None
    assert "crosscheck" in payload["transit_bazi"]["source"] or "lunar-python" in payload["transit_bazi"]["source"]
