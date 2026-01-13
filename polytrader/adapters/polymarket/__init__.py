"""Polymarket venue adapters.

This package contains adapters for Polymarket venue:
- Market data adapter (Gamma API)
- Trading adapter (CLOB API)

Note: PolymarketAdapterConfig and PolymarketMarketDataAdapter are defined
in polytrader.adapters.polymarket (the module file, not this package).
Import them directly from there when needed.
"""

from polytrader.adapters.polymarket.market_data import GammaClient, Market
from polytrader.adapters.polymarket.models import (
    BestBidAskMessage,
    BookMessage,
    CanonicalCancel,
    CanonicalFill,
    CanonicalOrderAck,
    CanonicalOrderReject,
    EventMessage,
    ExternalOrder,
    LastTradePriceMessage,
    MakerOrder,
    MarketResolvedMessage,
    NewMarketMessage,
    OrderMessage,
    OrderSummary,
    PriceChange,
    PriceChangeMessage,
    TickSizeChangeMessage,
    TradeMessage,
    VenueError,
    VenueResponse,
    WebSocketMessage,
    parse_websocket_message,
)
from polytrader.adapters.polymarket.trading import ClobVenueAdapter
from polytrader.adapters.polymarket.user_stream import UserStreamAdapter

__all__ = [
    "BestBidAskMessage",
    "BookMessage",
    "CanonicalCancel",
    "CanonicalFill",
    "CanonicalOrderAck",
    "CanonicalOrderReject",
    "ClobVenueAdapter",
    "EventMessage",
    "ExternalOrder",
    "GammaClient",
    "LastTradePriceMessage",
    "MakerOrder",
    "Market",
    "MarketResolvedMessage",
    "NewMarketMessage",
    "OrderMessage",
    "OrderSummary",
    "parse_websocket_message",
    "PriceChange",
    "PriceChangeMessage",
    "TickSizeChangeMessage",
    "TradeMessage",
    "UserStreamAdapter",
    "VenueError",
    "VenueResponse",
    "WebSocketMessage",
]
