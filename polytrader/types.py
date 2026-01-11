from typing import Literal

# Domain types only - no event classes (moved to events/types.py)
# This breaks the circular dependency: types.py no longer imports from events/types.py

Outcome = Literal["UP", "DOWN"]
Side = Literal["BUY", "SELL"]


class Position:
    """Active trading position.

    Attributes:
        market_slug: Market identifier
        outcome: Outcome ("UP" or "DOWN")
        size: Position size in USD
        target_price: Target price to sell at
        entry_price: Price when position was opened
        entry_time: Timestamp when position was opened
        order_id: ID of the BUY order that opened this position
    """

    def __init__(
        self,
        market_slug: str,
        outcome: Outcome,
        size: float,
        target_price: float,
        entry_price: float,
        entry_time: float,
        order_id: str | None = None,
    ) -> None:
        """Initialize Position."""
        self.market_slug = market_slug
        self.outcome = outcome
        self.size = size
        self.target_price = target_price
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.order_id = order_id
