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
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make a trading decision.

        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current mid price for UP outcome
            down_price: Current mid price for DOWN outcome

        Returns:
            TradeDecision or list of TradeDecisions if trades should be made, None otherwise
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

    def __str__(self) -> str:
        """String representation of the strategy."""
        return (
            f"RandomStrategy(trade_probability={self.trade_probability:.1%}, "
            f"amount_range=${self.min_trade_amount:.2f}-${self.max_trade_amount:.2f})"
        )

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


class ArbitrageStrategy:
    """Arbitrage trading strategy that builds positions on both UP and DOWN outcomes.
    
    This strategy actively builds positions while accepting risk that arbitrage may never
    be created. It limits risk exposure via max_capital_per_market and minimizes loss by
    only executing trades that improve guaranteed profit.
    """

    def __init__(
        self,
        max_capital_per_market: float = 100.0,
        initial_position_pct: float = 0.1,
        min_profit_threshold: float = 5.0,
        max_price_threshold: float = 0.91,
        trade_amount: float = 10.0,
        min_improvement: float = 0.10,
    ) -> None:
        """Initialize arbitrage strategy.

        Args:
            max_capital_per_market: Risk limit - Maximum capital per market (default: $100)
            initial_position_pct: Percentage of capital for initial positions (default: 0.1 = 10% per side)
            min_profit_threshold: Minimum profit threshold (default: $5) - if profit exceeds this, don't trade
            max_price_threshold: Maximum price threshold (default: 0.91) - don't trade if either price exceeds this
            trade_amount: Fixed amount per trade (default: $10)
            min_improvement: Minimum improvement in guaranteed profit required (default: $0.10)
        """
        self.max_capital_per_market = max_capital_per_market
        self.initial_position_pct = initial_position_pct
        self.min_profit_threshold = min_profit_threshold
        self.max_price_threshold = max_price_threshold
        self.trade_amount = trade_amount
        self.min_improvement = min_improvement

    def __str__(self) -> str:
        """String representation of the strategy."""
        return (
            f"ArbitrageStrategy(max_capital=${self.max_capital_per_market:.2f}, "
            f"initial_pct={self.initial_position_pct:.1%}, "
            f"trade_amount=${self.trade_amount:.2f}, "
            f"min_improvement=${self.min_improvement:.2f})"
        )

    def _calculate_net_arbitrage_profit(
        self, up_position: "Position | None", down_position: "Position | None"
    ) -> float:
        """Calculate net arbitrage profit (guaranteed profit).
        
        Args:
            up_position: UP position or None
            down_position: DOWN position or None
            
        Returns:
            Guaranteed profit (minimum shares * $1.00 - total cost)
        """
        total_cost = (
            (up_position.quantity * up_position.avg_price if up_position else 0)
            + (down_position.quantity * down_position.avg_price if down_position else 0)
        )

        up_shares = up_position.quantity if up_position else 0
        down_shares = down_position.quantity if down_position else 0

        # Guaranteed profit = minimum shares * $1.00 - total cost
        guaranteed_profit = min(up_shares, down_shares) * 1.0 - total_cost
        return guaranteed_profit

    def _calculate_profit_after_trade(
        self,
        up_position: "Position | None",
        down_position: "Position | None",
        outcome: "Outcome",
        amount: float,
        price: float,
    ) -> float:
        """Calculate guaranteed profit after adding a trade.
        
        Args:
            up_position: Current UP position or None
            down_position: Current DOWN position or None
            outcome: Outcome to buy ("UP" or "DOWN")
            amount: Amount in USDC to spend
            price: Price per share
            
        Returns:
            New guaranteed profit after the trade
        """
        total_cost = (
            (up_position.quantity * up_position.avg_price if up_position else 0)
            + (down_position.quantity * down_position.avg_price if down_position else 0)
        )

        if outcome == "UP":
            new_up_shares = (up_position.quantity if up_position else 0) + (amount / price)
            new_down_shares = down_position.quantity if down_position else 0
            new_total_cost = total_cost + amount
        else:  # DOWN
            new_up_shares = up_position.quantity if up_position else 0
            new_down_shares = (down_position.quantity if down_position else 0) + (amount / price)
            new_total_cost = total_cost + amount

        new_guaranteed_profit = min(new_up_shares, new_down_shares) * 1.0 - new_total_cost
        return new_guaranteed_profit

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make a trading decision.

        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current mid price for UP outcome
            down_price: Current mid price for DOWN outcome

        Returns:
            TradeDecision, list of TradeDecisions, or None
        """
        from polytrader.types import Outcome

        # Check constraints
        if up_price > self.max_price_threshold or down_price > self.max_price_threshold:
            return None

        # Validate price consistency: UP + DOWN should be close to 1.0
        # If deviation > 0.3, it's likely a bug/data issue, don't trade
        price_sum = up_price + down_price
        if abs(price_sum - 1.0) > 0.3:
            return None

        # Get existing positions
        up_position = portfolio.get_position(market_id, "UP")
        down_position = portfolio.get_position(market_id, "DOWN")

        # Calculate total cost of existing positions
        total_cost = (
            (up_position.quantity * up_position.avg_price if up_position else 0)
            + (down_position.quantity * down_position.avg_price if down_position else 0)
        )

        # Check risk limit
        if total_cost >= self.max_capital_per_market:
            return None

        # Calculate current guaranteed profit
        current_profit = self._calculate_net_arbitrage_profit(up_position, down_position)

        # Check profit threshold
        if current_profit >= self.min_profit_threshold:
            return None

        # Handle initial positions (no existing positions)
        if up_position is None and down_position is None:
            # Calculate initial capital (respecting max_capital_per_market)
            initial_capital_per_side = self.max_capital_per_market * self.initial_position_pct

            # Check if we have enough balance
            if initial_capital_per_side * 2 > portfolio.balance:
                initial_capital_per_side = portfolio.balance / 2

            if initial_capital_per_side < 0.01:  # Minimum trade size
                return None

            # Return both trades simultaneously
            return [
                TradeDecision(
                    market_id=market_id,
                    outcome="UP",
                    amount=initial_capital_per_side,
                    price=up_price,
                ),
                TradeDecision(
                    market_id=market_id,
                    outcome="DOWN",
                    amount=initial_capital_per_side,
                    price=down_price,
                ),
            ]

        # Handle ongoing trades (existing positions)
        # Check if adding trade_amount would exceed max_capital_per_market
        if total_cost + self.trade_amount > self.max_capital_per_market:
            return None

        # Check if we have enough balance
        if self.trade_amount > portfolio.balance:
            return None

        # Try buying UP
        up_profit_after = self._calculate_profit_after_trade(
            up_position, down_position, "UP", self.trade_amount, up_price
        )
        up_improvement = up_profit_after - current_profit

        # Try buying DOWN
        down_profit_after = self._calculate_profit_after_trade(
            up_position, down_position, "DOWN", self.trade_amount, down_price
        )
        down_improvement = down_profit_after - current_profit

        # Choose the trade that improves guaranteed profit most
        if (
            up_improvement >= self.min_improvement
            and up_improvement > down_improvement
        ):
            return TradeDecision(
                market_id=market_id,
                outcome="UP",
                amount=self.trade_amount,
                price=up_price,
            )

        if (
            down_improvement >= self.min_improvement
            and down_improvement > up_improvement
        ):
            return TradeDecision(
                market_id=market_id,
                outcome="DOWN",
                amount=self.trade_amount,
                price=down_price,
            )

        # If neither trade improves by min_improvement, don't trade
        return None

