from __future__ import annotations

from fastapi import FastAPI

from .debug_routes import register_market_debug_routes
from .health_routes import register_market_health_routes
from .top_markets_routes import register_market_top_markets_routes


def register_market_meta_routes(app: FastAPI) -> None:
    register_market_health_routes(app)
    register_market_debug_routes(app)
    register_market_top_markets_routes(app)
