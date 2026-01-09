"""Gabagool V6 Strategy - V4 with automatic hedging when worst-case loss exceeds threshold.

Strategy:
- Same as V4: When any side hits winner_threshold (default 0.6), declare it as winner
- Buy enough of that side so the portfolio makes target_profit_usdc profit if it wins
- If price is above max_buy_price, don't buy
- If declared winner changes or price drops below threshold, reset and allow new declaration
- If a trade would cause worst-case loss > threshold, hedge by buying both sides to breakeven
"""

from dataclasses import dataclass

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision
from polytrader.types import CandleData


@dataclass
class GabagoolV6State:
    """Tracks state for gabagool V6 strategy per market."""

    declared_winner: str | None = None  # "UP" or "DOWN" or None
    buy_done: bool = False  # Whether we've made the buy for current declared winner


class GabagoolV6Strategy:
    """V4 strategy with automatic hedging when worst-case loss exceeds threshold.
    
    Strategy:
    - Same as V4: When any side hits winner_threshold, declare it as winner
    - Buy enough of that side so portfolio makes target_profit_usdc profit if it wins
    - If price is above max_buy_price, don't buy
    - If declared winner changes or price drops below threshold, reset and allow new declaration
    - If a trade would cause worst-case loss > threshold, hedge by buying both sides to breakeven
    """

    def __init__(
        self,
        target_profit_usdc: float = 10.0,
        winner_threshold: float = 0.6,
        max_buy_price: float = 0.65,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 500.0,
        worst_case_loss_threshold: float = 100.0,
    ) -> None:
        self.target_profit_usdc = target_profit_usdc
        self.winner_threshold = winner_threshold
        self.max_buy_price = max_buy_price
        self.min_trade_amount_usdc = min_trade_amount_usdc
        self.max_capital_per_market_usdc = max_capital_per_market_usdc
        self.worst_case_loss_threshold = worst_case_loss_threshold

        # Per-market state
        self.market_states: dict[str, GabagoolV6State] = {}

    def _get_state(self, market_id: str) -> GabagoolV6State:
        """Get or create state for a market."""
        if market_id not in self.market_states:
            self.market_states[market_id] = GabagoolV6State()
        return self.market_states[market_id]

    def _calculate_worst_case_loss(
        self,
        portfolio: Portfolio,
        market_id: str,
    ) -> float:
        """Calculate worst-case loss if the opposite outcome wins.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            
        Returns:
            Worst-case loss in USDC (negative means profit)
        """
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        # Calculate total cost
        total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        # Calculate profit if UP wins and if DOWN wins
        profit_if_up_wins = (up_pos.quantity * 1.0 if up_pos else 0.0) - total_cost
        profit_if_down_wins = (down_pos.quantity * 1.0 if down_pos else 0.0) - total_cost
        
        # Worst case is the minimum (most negative) profit
        return min(profit_if_up_wins, profit_if_down_wins)

    def _calculate_breakeven_hedge(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> tuple[float, float]:
        """Calculate amounts to buy of both sides to achieve breakeven.
        
        We want to minimize cost while ensuring both outcomes result in ~$0 profit.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current UP price
            down_price: Current DOWN price
            
        Returns:
            Tuple of (up_amount, down_amount) in USDC to spend
        """
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        # Current positions
        current_up_shares = up_pos.quantity if up_pos else 0.0
        current_down_shares = down_pos.quantity if down_pos else 0.0
        
        # Current total cost
        current_total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        # We want: (current_up_shares + new_up_shares) * 1.0 - (current_total_cost + new_cost) ≈ 0
        # And: (current_down_shares + new_down_shares) * 1.0 - (current_total_cost + new_cost) ≈ 0
        
        # Target: both outcomes should result in ~$0 profit
        # This means we need: total_shares * $1.00 ≈ total_cost
        
        # If we buy up_amount of UP and down_amount of DOWN:
        # new_up_shares = up_amount / up_price
        # new_down_shares = down_amount / down_price
        # new_cost = up_amount + down_amount
        
        # For breakeven:
        # (current_up_shares + new_up_shares) * 1.0 = current_total_cost + new_cost
        # (current_down_shares + new_down_shares) * 1.0 = current_total_cost + new_cost
        
        # Solving: we want both sides to have equal shares after buying
        # Let target_shares = current_total_cost (so payout = cost)
        target_shares = current_total_cost
        
        # Calculate how many more shares we need for each side
        needed_up_shares = max(0.0, target_shares - current_up_shares)
        needed_down_shares = max(0.0, target_shares - current_down_shares)
        
        # Convert to amounts
        up_amount = needed_up_shares * up_price if needed_up_shares > 0 else 0.0
        down_amount = needed_down_shares * down_price if needed_down_shares > 0 else 0.0
        
        return (up_amount, down_amount)

    def _check_target_profit_reached(
        self,
        portfolio: Portfolio,
        market_id: str,
        outcome: str,
    ) -> bool:
        """Check if portfolio has reached target profit for the given outcome.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            outcome: "UP" or "DOWN" - the outcome to check
            
        Returns:
            True if target profit is reached, False otherwise
        """
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
        
        return current_profit >= self.target_profit_usdc

    def _calculate_amount_for_portfolio_profit(
        self,
        portfolio: Portfolio,
        market_id: str,
        outcome: str,
        price: float,
    ) -> float:
        """Calculate amount to buy so portfolio makes target profit if outcome wins.
        
        Accounts for existing positions in the portfolio. This will recalculate based
        on current portfolio state, handling partial fills correctly.
        
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
        state: GabagoolV6State,
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
        state: GabagoolV6State,
        outcome: str,
        price: float,
        opposite_price: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Process a single outcome (UP or DOWN) and return trade decision if needed.
        
        Assumes price is already validated to be at threshold and within buy price range.
        
        Handles partial fills by checking if target profit is reached after each fill.
        If we got a partial fill, buy_done will be reset and we'll recalculate on next tick.
        
        Args:
            portfolio: Current portfolio state (may have been updated with partial fills)
            market_id: Market identifier
            state: Current market state
            outcome: "UP" or "DOWN"
            price: Current price of the outcome
            opposite_price: Current price of the opposite outcome (for hedging)
            
        Returns:
            TradeDecision or list of TradeDecisions if we should buy, None otherwise
        """
        # Declare winner if needed
        if state.declared_winner != outcome:
            state.declared_winner = outcome
            state.buy_done = False
        
        # Check if we've already reached target profit with current portfolio state
        # This handles partial fills: if we got a partial fill, portfolio was updated
        # on the previous tick, and now we check again. If target profit is reached
        # (either from full fill or cumulative partial fills), we're done.
        if self._check_target_profit_reached(portfolio, market_id, outcome):
            state.buy_done = True
            return None
        
        # If target profit not reached, ensure buy_done is False so we can buy more
        # This handles partial fills: if we got a partial fill on the previous tick,
        # buy_done might have been True, but we haven't reached target profit yet,
        # so we need to recalculate and buy more with the updated portfolio
        state.buy_done = False
        
        # Calculate amount to buy based on current portfolio state
        # This will account for any partial fills we received
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
        
        # Simulate the trade to check worst-case loss
        # Create a temporary portfolio state with the proposed trade
        from polytrader.core.position import Position
        
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        # Simulate adding the new position
        new_shares = amount / price
        if outcome == "UP":
            simulated_up_shares = (up_pos.quantity if up_pos else 0.0) + new_shares
            simulated_down_shares = down_pos.quantity if down_pos else 0.0
            simulated_total_cost = (
                (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
                + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
                + amount
            )
        else:  # DOWN
            simulated_up_shares = up_pos.quantity if up_pos else 0.0
            simulated_down_shares = (down_pos.quantity if down_pos else 0.0) + new_shares
            simulated_total_cost = (
                (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
                + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
                + amount
            )
        
        # Calculate worst-case loss after this trade
        profit_if_up_wins = (simulated_up_shares * 1.0) - simulated_total_cost
        profit_if_down_wins = (simulated_down_shares * 1.0) - simulated_total_cost
        worst_case_loss = min(profit_if_up_wins, profit_if_down_wins)
        
        # If worst-case loss exceeds threshold, hedge instead
        if worst_case_loss < -self.worst_case_loss_threshold and opposite_price is not None:
            # Calculate breakeven hedge
            up_amount, down_amount = self._calculate_breakeven_hedge(
                portfolio, market_id, price if outcome == "UP" else opposite_price, 
                opposite_price if outcome == "UP" else price
            )
            
            # Ensure we have the correct prices
            actual_up_price = price if outcome == "UP" else opposite_price
            actual_down_price = opposite_price if outcome == "UP" else price
            
            hedge_trades: list[TradeDecision] = []
            
            if up_amount > 0 and up_amount >= self.min_trade_amount_usdc:
                if portfolio.balance >= up_amount:
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="UP",
                            amount=up_amount,
                            price=actual_up_price,
                        )
                    )
            
            if down_amount > 0 and down_amount >= self.min_trade_amount_usdc:
                total_needed = up_amount + down_amount
                if portfolio.balance >= total_needed:
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=actual_down_price,
                        )
                    )
                elif portfolio.balance >= down_amount and up_amount == 0:
                    # Can only afford DOWN
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=actual_down_price,
                        )
                    )
            
            if hedge_trades:
                return hedge_trades if len(hedge_trades) > 1 else hedge_trades[0]
            # If we can't afford hedge, fall through to normal trade
        
        # Normal trade - make the trade (but don't set buy_done yet - will be set after trade executes
        # in on_trade_executed, or reset if we need more due to partial fill)
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
        
        # Check for reactive hedging first (if worst-case loss already exceeds threshold)
        worst_case_loss = self._calculate_worst_case_loss(portfolio, market_id)
        if worst_case_loss < -self.worst_case_loss_threshold:
            # Calculate breakeven hedge
            up_amount, down_amount = self._calculate_breakeven_hedge(
                portfolio, market_id, up_price, down_price
            )
            
            hedge_trades: list[TradeDecision] = []
            
            if up_amount > 0 and up_amount >= self.min_trade_amount_usdc and up_price <= self.max_buy_price:
                if portfolio.balance >= up_amount:
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="UP",
                            amount=up_amount,
                            price=up_price,
                        )
                    )
            
            if down_amount > 0 and down_amount >= self.min_trade_amount_usdc and down_price <= self.max_buy_price:
                total_needed = up_amount + down_amount
                if portfolio.balance >= total_needed:
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=down_price,
                        )
                    )
                elif portfolio.balance >= down_amount and up_amount == 0:
                    # Can only afford DOWN
                    hedge_trades.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=down_price,
                        )
                    )
            
            if hedge_trades:
                return hedge_trades if len(hedge_trades) > 1 else hedge_trades[0]
        
        # Process valid outcomes, prioritizing current declared winner if it's still valid
        if state.declared_winner == "UP" and up_valid:
            return self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
        elif state.declared_winner == "DOWN" and down_valid:
            return self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        elif up_valid and not down_valid:
            return self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
        elif down_valid and not up_valid:
            return self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        elif up_valid and down_valid:
            # Both valid - if we have a declared winner that's still valid, it was processed
            # on lines 249-252. If we reach here, either:
            # 1. No declared winner yet (state.declared_winner is None) - first time seeing both valid
            # 2. Declared winner was just reset to None (because it became invalid, then both became valid again)
            # In either case, pick the one with better price (lower is better for buying)
            if up_price <= down_price:
                return self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
            else:
                return self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        
        return None

    def on_trade_executed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called after a trade is successfully executed.
        
        Note: We don't set buy_done here because we don't have portfolio access.
        Instead, on the next decide() call, we'll check if target profit is reached
        based on the updated portfolio (which may have partial fills). If target
        profit is reached, buy_done will be set to True in _process_outcome.
        If not (partial fill), buy_done will remain False and we'll calculate
        the remaining amount needed.
        """
        # Don't set buy_done here - let the next decide() call check if target
        # profit is reached based on updated portfolio state (handles partial fills)
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
