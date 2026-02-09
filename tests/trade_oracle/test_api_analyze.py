from __future__ import annotations

from fastapi.testclient import TestClient

from trade_oracle.apps.api.main import app
from trade_oracle.market_client import MarketResponseError, MarketSourceUnavailableError
from trade_oracle.service import OracleService


client = TestClient(app)


def test_analyze_api_success(monkeypatch):
    def fake_analyze(self, *, series_id: str, symbol: str = "BTC"):
        payload = {
            "series_id": series_id,
            "generated_at_utc": "2026-02-09T00:00:00+00:00",
            "bias": "neutral",
            "confidence": "low",
            "total_score": 0.1,
            "historical_note": "ok",
            "factor_scores": [],
            "evidence": {},
        }
        return payload, "report"

    monkeypatch.setattr(OracleService, "analyze_current", fake_analyze)
    resp = client.get("/api/oracle/analyze/current", params={"series_id": "binance:futures:BTC/USDT:1d"})
    assert resp.status_code == 200
    assert resp.json()["series_id"] == "binance:futures:BTC/USDT:1d"


def test_analyze_api_market_unavailable(monkeypatch):
    def fake_analyze(self, *, series_id: str, symbol: str = "BTC"):
        raise MarketSourceUnavailableError("market_api_unreachable")

    monkeypatch.setattr(OracleService, "analyze_current", fake_analyze)
    resp = client.get("/api/oracle/analyze/current")
    assert resp.status_code == 503
    assert "market_source_unavailable" in resp.json()["detail"]


def test_analyze_api_market_5xx_maps_to_503(monkeypatch):
    def fake_analyze(self, *, series_id: str, symbol: str = "BTC"):
        raise MarketResponseError("http_status=502")

    monkeypatch.setattr(OracleService, "analyze_current", fake_analyze)
    resp = client.get("/api/oracle/analyze/current")
    assert resp.status_code == 503
    assert "market_source_unavailable" in resp.json()["detail"]
