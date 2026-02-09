from __future__ import annotations

import json
from pathlib import Path

from trade_oracle.config import OracleSettings
from trade_oracle.models import Candle, StrategyMetrics
from trade_oracle.service import OracleService


class _FakeMarket:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def fetch_candles(self, **kwargs) -> list[Candle]:
        return self._candles


def _mock_candles() -> list[Candle]:
    rows = json.loads(Path("trade_oracle/fixtures/btc_1d_mock_120.json").read_text(encoding="utf-8"))
    return [Candle(**r) for r in rows]


def _settings() -> OracleSettings:
    return OracleSettings(
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


def test_run_market_backtest_pass_flag_true():
    svc = OracleService(_settings())
    svc.market = _FakeMarket(_mock_candles())
    svc._run_backtest = lambda **kwargs: StrategyMetrics(
        trades=20,
        win_rate=0.62,
        profit_factor=1.9,
        avg_win=0.02,
        avg_loss=0.01,
        expectancy=0.004,
        reward_risk=2.4,
        threshold=0.6,
        windows=3,
    )

    result = svc.run_market_backtest(series_id="binance:futures:BTC/USDT:1d")
    assert result["passed"] is True
    assert result["metrics"]["reward_risk"] >= 2.0


def test_run_market_backtest_pass_flag_false_when_target_not_met():
    svc = OracleService(_settings())
    svc.market = _FakeMarket(_mock_candles())
    svc._run_backtest = lambda **kwargs: StrategyMetrics(
        trades=20,
        win_rate=0.45,
        profit_factor=1.1,
        avg_win=0.01,
        avg_loss=0.01,
        expectancy=0.0,
        reward_risk=1.0,
        threshold=0.8,
        windows=3,
    )

    result = svc.run_market_backtest(series_id="binance:futures:BTC/USDT:1d")
    assert result["passed"] is False
