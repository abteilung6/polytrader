"""Portfolio manager for executing trades."""

from polytrader.core.portfolio import Portfolio
from polytrader.core.strategy import ArbitrageStrategy, RandomStrategy, Strategy
from polytrader.core.trade import TradeDecision
from polytrader.types import MarketTick


class PortfolioManager:
    """Manages portfolio and executes trades based on strategy."""

    def __init__(self, initial_balance: float = 1000.0, strategy: Strategy | None = None) -> None:
        """Initialize portfolio manager.

        Args:
            initial_balance: Starting USDC balance
            strategy: Trading strategy to use (defaults to RandomStrategy)
        """
        self.portfolio = Portfolio(balance=initial_balance)
        self.strategy = strategy or RandomStrategy()
        self.total_trades = 0
        self.total_spent = 0.0

    def get_balance(self) -> float:
        """Get current USDC balance."""
        return self.portfolio.balance

    def get_portfolio(self) -> Portfolio:
        """Get current portfolio state."""
        return self.portfolio

    def process_tick(self, tick: MarketTick) -> TradeDecision | None:
        """Process a market tick and potentially execute a trade.

        Args:
            tick: Market tick with price data

        Returns:
            TradeDecision if a trade was made, None otherwise
        """
        # Get prices for both outcomes
        # Use best_ask (best_bid + spread) for buying - accounts for spread
        # For binary markets, UP + DOWN = 1.0, so we can calculate the other price
        if tick.outcome == "UP":
            up_price = tick.best_ask
            down_price = 1.0 - tick.best_ask  # Assuming binary market
        else:
            down_price = tick.best_ask
            up_price = 1.0 - tick.best_ask  # Assuming binary market

        # Get decision from strategy
        decision = self.strategy.decide(
            portfolio=self.portfolio,
            market_id=tick.market_id,
            up_price=up_price,
            down_price=down_price,
        )

        if decision is None:
            return None

        # Execute the trade (simulated)
        self._execute_trade(decision)

        return decision

    def process_prices(
        self,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Process prices for both outcomes and potentially execute a trade.

        This is useful when you have prices for both UP and DOWN outcomes.

        Args:
            market_id: Market identifier
            up_price: Current mid price for UP outcome
            down_price: Current mid price for DOWN outcome

        Returns:
            TradeDecision or list of TradeDecisions if trades were made, None otherwise
        """
        # Get decision from strategy
        decision = self.strategy.decide(
            portfolio=self.portfolio,
            market_id=market_id,
            up_price=up_price,
            down_price=down_price,
        )

        if decision is None:
            return None

        # Handle both single decision and list of decisions (for arbitrage)
        if isinstance(decision, list):
            # Execute all trades in the list
            for trade in decision:
                self._execute_trade(trade)
            return decision
        else:
            # Execute single trade
            self._execute_trade(decision)
            return decision

    def _execute_trade(self, decision: TradeDecision) -> None:
        """Execute a trade (simulated).

        Args:
            decision: Trade decision to execute
        """
        # Calculate quantity based on amount and price
        quantity = decision.amount / decision.price

        # Update portfolio
        self.portfolio.balance -= decision.amount
        self.portfolio.add_position(
            market_id=decision.market_id,
            outcome=decision.outcome,
            quantity=quantity,
            price=decision.price,
        )

        # Track statistics
        self.total_trades += 1
        self.total_spent += decision.amount

    def expire_positions(
        self,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> dict[str, float | int]:
        """Expire positions for a market and settle them.
        
        The outcome with the higher price wins (goes to $1.00), the other goes to $0.00.
        
        Args:
            market_id: Market identifier
            up_price: Latest price for UP outcome
            down_price: Latest price for DOWN outcome
            
        Returns:
            Dictionary with settlement information:
            - winner: "UP" or "DOWN"
            - positions_settled: number of positions settled
            - total_payout: total USDC added to balance
        """
        winner = "UP" if up_price > down_price else "DOWN"
        positions_settled = 0
        total_payout = 0.0
        
        # Find all positions for this market
        positions_to_remove: list[tuple[str, Outcome]] = []
        
        for (m_id, outcome), position in self.portfolio.positions.items():
            if m_id == market_id:
                positions_to_remove.append((m_id, outcome))
                
                # If this position's outcome matches the winner, pay out $1.00 per share
                if outcome == winner:
                    payout = position.quantity * 1.0
                    self.portfolio.balance += payout
                    total_payout += payout
                
                # If it's the loser, payout is $0.00 (nothing added to balance)
                positions_settled += 1
        
        # Remove expired positions
        for key in positions_to_remove:
            del self.portfolio.positions[key]
        
        return {
            "winner": winner,
            "positions_settled": positions_settled,
            "total_payout": total_payout,
        }

    def get_statistics(self) -> dict[str, float | int]:
        """Get portfolio statistics."""
        return {
            "balance": self.portfolio.balance,
            "total_trades": self.total_trades,
            "total_spent": self.total_spent,
            "num_positions": len(self.portfolio.positions),
        }

