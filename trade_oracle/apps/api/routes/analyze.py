from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from trade_oracle.apps.api.schemas import AnalyzeCurrentResponse
from trade_oracle.config import OracleSettings, load_settings
from trade_oracle.market_client import MarketClientError, MarketSourceUnavailableError
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
    service = OracleService(settings)
    try:
        payload, report_md = service.analyze_current(series_id=series_id, symbol=symbol)
    except MarketSourceUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "market_source_unavailable: 请先确认 trade_canvas 后端可访问 "
                f"({settings.market_api_base})，原始错误: {exc}"
            ),
        ) from exc
    except MarketClientError as exc:
        msg = str(exc)
        if msg.startswith("http_status=5"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "market_source_unavailable: trade_canvas 市场接口返回 5xx，"
                    f"请检查 backend 服务，原始错误: {msg}"
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"market_source_error:{msg}") from exc
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"unknown_asset:{exc}") from exc
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
