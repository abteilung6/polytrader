"""Trade decision representation."""

from dataclasses import dataclass

from polytrader.types import Outcome


@dataclass
class TradeDecision:
    """Represents a trading decision from a strategy."""

    market_id: str
    outcome: Outcome
    amount: float  # Amount in USDC to spend
    price: float  # Expected price (mid price or best ask)

