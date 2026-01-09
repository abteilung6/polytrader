"""Gabagool V4 Strategy - Simplified winner declaration and profit targeting.

Strategy:
- When any side hits winner_threshold (default 0.6), declare it as winner
- Buy enough of that side so the portfolio makes target_profit_usdc profit if it wins
- If price is above max_buy_price, don't buy
- If declared winner changes or price drops below threshold, reset and allow new declaration
"""

from dataclasses import dataclass

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision
from polytrader.types import CandleData


@dataclass
class GabagoolV4State:
    """Tracks state for gabagool V4 strategy per market."""

    declared_winner: str | None = None  # "UP" or "DOWN" or None
    buy_done: bool = False  # Whether we've made the buy for current declared winner


class GabagoolV4Strategy:
    """Simplified strategy that declares a winner at threshold and buys for target profit.
    
    Strategy:
    - When any side hits winner_threshold, declare it as winner
    - Buy enough of that side so portfolio makes target_profit_usdc profit if it wins
    - If price is above max_buy_price, don't buy
    - If declared winner changes or price drops below threshold, reset and allow new declaration
    """

    def __init__(
        self,
        target_profit_usdc: float = 10.0,
        winner_threshold: float = 0.6,
        max_buy_price: float = 0.65,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 500.0,
    ) -> None:
        self.target_profit_usdc = target_profit_usdc
        self.winner_threshold = winner_threshold
        self.max_buy_price = max_buy_price
        self.min_trade_amount_usdc = min_trade_amount_usdc
        self.max_capital_per_market_usdc = max_capital_per_market_usdc

        # Per-market state
        self.market_states: dict[str, GabagoolV4State] = {}

    def _get_state(self, market_id: str) -> GabagoolV4State:
        """Get or create state for a market."""
        if market_id not in self.market_states:
            self.market_states[market_id] = GabagoolV4State()
        return self.market_states[market_id]

    def _calculate_amount_for_portfolio_profit(
        self,
        portfolio: Portfolio,
        market_id: str,
        outcome: str,
        price: float,
    ) -> float:
        """Calculate amount to buy so portfolio makes target profit if outcome wins.
        
        Accounts for existing positions in the portfolio.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            outcome: "UP" or "DOWN" - the outcome we're buying
            price: Current price of the outcome
            
        Returns:
            Amount in USDC to spend, or 0.0 if already have enough profit
        """
        if price >= 1.0 or price <= 0:
            return 0.0
        
        # Get existing positions
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        # Calculate current portfolio state
        existing_total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        existing_shares = (
            up_pos.quantity if outcome == "UP" and up_pos else
            down_pos.quantity if outcome == "DOWN" and down_pos else
            0.0
        )
        
        # Calculate current profit if this outcome wins
        current_profit = (existing_shares * 1.0) - existing_total_cost
        
        # If we already make enough profit, don't buy more
        if current_profit >= self.target_profit_usdc:
            return 0.0
        
        # Calculate how much more profit we need
        needed_profit = self.target_profit_usdc - current_profit
        
        # Calculate amount to buy: amount * (1 - price) / price = needed_profit
        # Solving for amount: amount = needed_profit * price / (1 - price)
        return needed_profit * price / (1.0 - price)

    def _check_and_reset_winner(
        self,
        state: GabagoolV4State,
        outcome: str,
        price: float,
    ) -> None:
        """Reset declared winner if this outcome's price is too high or below threshold.
        
        Only resets if this outcome was the declared winner.
        
        Args:
            state: Current market state
            outcome: "UP" or "DOWN"
            price: Current price of the outcome
        """
        # Only reset if this outcome was the declared winner
        if state.declared_winner == outcome:
            # Price too high or below threshold - reset
            if price > self.max_buy_price or price < self.winner_threshold:
                state.declared_winner = None
                state.buy_done = False

    def _process_outcome(
        self,
        portfolio: Portfolio,
        market_id: str,
        state: GabagoolV4State,
        outcome: str,
        price: float,
    ) -> TradeDecision | None:
        """Process a single outcome (UP or DOWN) and return trade decision if needed.
        
        Assumes price is already validated to be at threshold and within buy price range.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            state: Current market state
            outcome: "UP" or "DOWN"
            price: Current price of the outcome
            
        Returns:
            TradeDecision if we should buy, None otherwise
        """
        # Declare winner if needed
        if state.declared_winner != outcome:
            state.declared_winner = outcome
            state.buy_done = False
        
        # If we already bought for this winner, don't buy again
        if state.buy_done:
            return None
        
        # Calculate amount to buy
        amount = self._calculate_amount_for_portfolio_profit(
            portfolio, market_id, outcome, price
        )
        
        # If amount is too small, we already have enough profit
        if amount <= 0 or amount < self.min_trade_amount_usdc:
            state.buy_done = True
            return None
        
        # Check if we have enough balance
        if portfolio.balance < amount:
            return None
        
        # Make the trade
        state.buy_done = True
        return TradeDecision(
            market_id=market_id,
            outcome=outcome,
            amount=amount,
            price=price,
        )

    def _get_total_invested(self, portfolio: Portfolio, market_id: str) -> float:
        """Calculate total capital invested in this market.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            
        Returns:
            Total amount invested in USDC
        """
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        total = 0.0
        if up_pos:
            total += up_pos.quantity * up_pos.avg_price
        if down_pos:
            total += down_pos.quantity * down_pos.avg_price
        
        return total

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make trading decision based on price thresholds.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current best ask price for UP outcome
            down_price: Current best ask price for DOWN outcome
            timestamp: Optional timestamp for backtesting
            : Optional ETH/USD candle data (OHLCV) for price context
        """
        # Early exit checks
        if portfolio.balance < self.min_trade_amount_usdc:
            return None
        
        if up_price <= 0 or down_price <= 0:
            return None
        
        if self._get_total_invested(portfolio, market_id) >= self.max_capital_per_market_usdc:
            return None
        
        state = self._get_state(market_id)
        
        # Check which outcomes are at threshold and within buy price range
        up_valid = up_price >= self.winner_threshold and up_price <= self.max_buy_price
        down_valid = down_price >= self.winner_threshold and down_price <= self.max_buy_price
        
        # Reset winners that are no longer valid
        if not up_valid:
            self._check_and_reset_winner(state, "UP", up_price)
        if not down_valid:
            self._check_and_reset_winner(state, "DOWN", down_price)
        
        # Process valid outcomes, prioritizing current declared winner if it's still valid
        if state.declared_winner == "UP" and up_valid:
            return self._process_outcome(portfolio, market_id, state, "UP", up_price)
        elif state.declared_winner == "DOWN" and down_valid:
            return self._process_outcome(portfolio, market_id, state, "DOWN", down_price)
        elif up_valid and not down_valid:
            return self._process_outcome(portfolio, market_id, state, "UP", up_price)
        elif down_valid and not up_valid:
            return self._process_outcome(portfolio, market_id, state, "DOWN", down_price)
        elif up_valid and down_valid:
            # Both valid - if we have a declared winner that's still valid, it was processed
            # on lines 249-252. If we reach here, either:
            # 1. No declared winner yet (state.declared_winner is None) - first time seeing both valid
            # 2. Declared winner was just reset to None (because it became invalid, then both became valid again)
            # In either case, pick the one with better price (lower is better for buying)
            if up_price <= down_price:
                return self._process_outcome(portfolio, market_id, state, "UP", up_price)
            else:
                return self._process_outcome(portfolio, market_id, state, "DOWN", down_price)
        
        return None

    def on_trade_executed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called after a trade is successfully executed."""
        # State is already updated in decide() method
        pass

    def on_trade_failed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called when a trade execution fails."""
        state = self._get_state(market_id)
        
        # Reset the buy flag to allow retry
        if state.declared_winner == outcome and state.buy_done:
            state.buy_done = False
