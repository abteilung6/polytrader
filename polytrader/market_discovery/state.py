"""Market state enumeration and validation."""

from enum import Enum


class MarketState(str, Enum):
    """Market state enumeration.

    Represents the actual state of a market for trading purposes.
    """

    ACTIVE = "active"  # Market exists and is tradeable
    EXPIRED = "expired"  # Market exists but time window has passed
    RESOLVED = "resolved"  # Market has been resolved
    NO_ORDERBOOK = "no_orderbook"  # Market exists but no orderbook
    NOT_FOUND = "not_found"  # Market doesn't exist
