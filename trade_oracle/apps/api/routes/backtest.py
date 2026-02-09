from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trade_oracle.config import load_settings
from trade_oracle.market_client import MarketClientError, MarketSourceUnavailableError
from trade_oracle.service import OracleService

router = APIRouter(prefix="/api/oracle", tags=["oracle"])


@router.get("/backtest/run")
def backtest_run(
    series_id: str = Query("binance:futures:BTC/USDT:1d", min_length=1),
    symbol: str = Query("BTC", min_length=1),
) -> dict:
    settings = load_settings()
    if not settings.enable_backtest:
        raise HTTPException(status_code=404, detail="backtest_disabled")

    service = OracleService(settings)
    try:
        result = service.run_market_backtest(series_id=series_id, symbol=symbol)
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"backtest_failed:{exc}") from exc

    if int(result.get("metrics", {}).get("trades", 0)) <= 0:
        raise HTTPException(status_code=422, detail="insufficient_data_for_walk_forward")
    return {"ok": True, **result}
