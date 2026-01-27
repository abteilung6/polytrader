"""Market data API routes.

Per PROPOSAL_MARKET_DATA_API.md: REST API endpoints for market tick data.
Provides endpoints for querying market data (latest ticks, historical ticks, market list).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/market", tags=["market"])
