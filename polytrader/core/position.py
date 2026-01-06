"""Position representation."""

from dataclasses import dataclass

from polytrader.types import Outcome


@dataclass
class Position:
    """Represents a position in a market outcome."""

    market_id: str
    outcome: Outcome
    quantity: float  # Number of shares/contracts
    avg_price: float  # Average price paid

