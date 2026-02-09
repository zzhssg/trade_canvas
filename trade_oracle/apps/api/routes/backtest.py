from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trade_oracle.config import load_settings
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
    result = service.run_market_backtest(series_id=series_id, symbol=symbol)
    if int(result.get("metrics", {}).get("trades", 0)) <= 0:
        raise HTTPException(status_code=422, detail="insufficient_data_for_walk_forward")
    return {"ok": True, **result}
