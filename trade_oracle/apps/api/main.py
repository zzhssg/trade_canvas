from __future__ import annotations

from fastapi import FastAPI

from .routes.analyze import router as analyze_router
from .routes.backtest import router as backtest_router

app = FastAPI(title="trade_oracle API", version="0.1.0")
app.include_router(analyze_router)
app.include_router(backtest_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"ok": "1"}
