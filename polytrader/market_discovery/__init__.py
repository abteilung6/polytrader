"""Market discovery service for finding active recurring markets.

This module provides functionality for discovering active markets from patterns,
validating market state, and managing market discovery operations.
"""

from polytrader.market_discovery.errors import (
    DiscoveryError,
    FatalDiscoveryError,
    RetryableDiscoveryError,
)
from polytrader.market_discovery.patterns import MarketPattern
from polytrader.market_discovery.service import IMarketDiscoveryService, MarketDiscoveryService
from polytrader.market_discovery.state import MarketState

__all__ = [
    "DiscoveryError",
    "FatalDiscoveryError",
    "IMarketDiscoveryService",
    "MarketDiscoveryService",
    "MarketPattern",
    "MarketState",
    "RetryableDiscoveryError",
]
