"""Polymarket venue adapters.

This package contains adapters for Polymarket venue:
- Market data adapter (Gamma API)
- Trading adapter (CLOB API)

Note: PolymarketAdapterConfig and PolymarketMarketDataAdapter are defined
in polytrader.adapters.polymarket (the module file, not this package).
Import them directly from there when needed.
"""

from polytrader.adapters.polymarket.market_data import GammaClient, Market
from polytrader.adapters.polymarket.models import ExternalOrder, VenueError, VenueResponse
from polytrader.adapters.polymarket.trading import ClobVenueAdapter

__all__ = [
    "ClobVenueAdapter",
    "ExternalOrder",
    "GammaClient",
    "Market",
    "VenueError",
    "VenueResponse",
]
