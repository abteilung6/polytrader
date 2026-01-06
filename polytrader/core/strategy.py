"""Trading strategy protocol and implementations."""

import random
from typing import Protocol

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision


class Strategy(Protocol):
    """Protocol for trading strategies."""

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> TradeDecision | None:
        """Make a trading decision.

        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current mid price for UP outcome
            down_price: Current mid price for DOWN outcome

        Returns:
            TradeDecision if a trade should be made, None otherwise
        """
        ...


class RandomStrategy:
    """Random trading strategy - randomly buys UP or DOWN outcomes."""

    def __init__(
        self,
        min_trade_amount: float = 1.0,
        max_trade_amount: float = 10.0,
        trade_probability: float = 0.1,
    ) -> None:
        """Initialize random strategy.

        Args:
            min_trade_amount: Minimum trade amount in USDC
            max_trade_amount: Maximum trade amount in USDC
            trade_probability: Probability of making a trade (0.0 to 1.0)
        """
        self.min_trade_amount = min_trade_amount
        self.max_trade_amount = max_trade_amount
        self.trade_probability = trade_probability

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> TradeDecision | None:
        """Randomly decide to buy UP or DOWN outcome."""
        # Check if we should make a trade
        if random.random() > self.trade_probability:
            return None

        # Check if we have enough balance
        trade_amount = random.uniform(self.min_trade_amount, self.max_trade_amount)
        if trade_amount > portfolio.balance:
            return None

        # Randomly choose UP or DOWN
        from polytrader.types import Outcome

        outcome: Outcome = "UP" if random.random() < 0.5 else "DOWN"
        price = up_price if outcome == "UP" else down_price

        return TradeDecision(
            market_id=market_id,
            outcome=outcome,
            amount=trade_amount,
            price=price,
        )

