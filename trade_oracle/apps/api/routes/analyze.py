from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from trade_oracle.apps.api.schemas import AnalyzeCurrentResponse
from trade_oracle.config import OracleSettings, load_settings
from trade_oracle.service import OracleService

router = APIRouter(prefix="/api/oracle", tags=["oracle"])


def get_settings() -> OracleSettings:
    return load_settings()


@router.get("/analyze/current", response_model=AnalyzeCurrentResponse)
def analyze_current(
    series_id: str = Query("binance:futures:BTC/USDT:1d", min_length=1),
    symbol: str = Query("BTC", min_length=1),
    settings: OracleSettings = Depends(get_settings),
) -> AnalyzeCurrentResponse:
    try:
        service = OracleService(settings)
        payload, report_md = service.analyze_current(series_id=series_id, symbol=symbol)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis_failed:{exc}") from exc

    return AnalyzeCurrentResponse(
        series_id=payload["series_id"],
        generated_at_utc=payload["generated_at_utc"],
        bias=payload["bias"],
        confidence=payload["confidence"],
        total_score=float(payload["total_score"]),
        historical_note=payload["historical_note"],
        report_markdown=report_md,
        evidence=payload,
    )
