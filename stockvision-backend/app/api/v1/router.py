"""
API v1 router assembly.

CHANGE LOG (v2.0): the `auth` router is gone. Eleven routers are registered where
there were six; ordering matters only in that a more specific prefix must be
included before one that could shadow it.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    copilot,
    market,
    ml,
    news,
    portfolios,
    reports,
    risk,
    stocks,
    system,
    watchlist,
)

api_router = APIRouter()

# Market data & overview
api_router.include_router(market.markets_router)
api_router.include_router(market.router)
api_router.include_router(stocks.router)

# Analytics
api_router.include_router(portfolios.router)
api_router.include_router(risk.router)
api_router.include_router(ml.router)

# Content & tooling
api_router.include_router(news.router)
api_router.include_router(watchlist.router)
api_router.include_router(copilot.router)
api_router.include_router(reports.router)

# Platform
api_router.include_router(system.router)
api_router.include_router(admin.router)
