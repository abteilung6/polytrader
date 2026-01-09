"""Trading strategy protocol and implementations."""

from typing import Protocol

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision
from polytrader.types import CandleData


class Strategy(Protocol):
    """Protocol for trading strategies."""

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make a trading decision.

        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current best ask price (best bid + spread) for UP outcome
            down_price: Current best ask price (best bid + spread) for DOWN outcome
            timestamp: Optional timestamp for backtesting (defaults to None, uses current time)

        Returns:
            TradeDecision or list of TradeDecisions if trades should be made, None otherwise
        """
        ...
    
    def on_trade_executed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called after a trade is successfully executed.
        
        This allows the strategy to update internal state (like rate limiting)
        only when trades actually succeed, not when they fail.
        
        Args:
            market_id: Market identifier
            outcome: Outcome that was traded ("UP" or "DOWN")
            price: Price at which the trade was executed
            timestamp: Optional timestamp for backtesting (defaults to None, uses current time)
        """
        ...  # Optional - strategies can implement this if they need it
