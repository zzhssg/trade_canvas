from __future__ import annotations

from fastapi.testclient import TestClient

from trade_oracle.apps.api.main import app
from trade_oracle.service import OracleService


client = TestClient(app)


def test_backtest_api_returns_metrics(monkeypatch):
    monkeypatch.setenv("TRADE_ORACLE_ENABLE_BACKTEST", "1")

    def fake_run(self, *, series_id: str, symbol: str = "BTC") -> dict:
        return {
            "series_id": series_id,
            "symbol": symbol,
            "generated_at_utc": "2026-02-09T00:00:00+00:00",
            "target": {"win_rate": 0.5, "reward_risk": 2.0},
            "settings": {"market_limit": 2000, "wf_train_size": 90, "wf_test_size": 30, "trade_fee_rate": 0.0008},
            "metrics": {
                "trades": 12,
                "win_rate": 0.6,
                "profit_factor": 1.5,
                "avg_win": 0.02,
                "avg_loss": 0.01,
                "expectancy": 0.004,
                "reward_risk": 2.0,
                "threshold": 0.8,
                "windows": 3,
            },
            "passed": True,
        }

    monkeypatch.setattr(OracleService, "run_market_backtest", fake_run)

    resp = client.get("/api/oracle/backtest/run", params={"series_id": "binance:futures:BTC/USDT:1d"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["metrics"]["trades"] == 12
    assert payload["passed"] is True
