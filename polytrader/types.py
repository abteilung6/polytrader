"""Core types for market data."""

from dataclasses import dataclass
from typing import Literal

Outcome = Literal["UP", "DOWN"]


@dataclass(frozen=True)
class MarketTick:
    """Market data tick with bid/ask prices.

    Attributes:
        ts: Unix timestamp in seconds (float for precision)
        market_id: Market identifier (e.g., market slug)
        outcome: Market outcome ("UP" or "DOWN")
        best_bid: Best bid price (what buyers offer, from side=SELL)
        best_ask: Best ask price (what sellers ask, from side=BUY)
    """

    ts: float
    market_id: str
    outcome: Outcome
    best_bid: float
    best_ask: float

    @property
    def mid(self) -> float:
        """Mid-market price (average of bid and ask)."""
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.best_ask - self.best_bid
