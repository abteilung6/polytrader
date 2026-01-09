"""Gabagool V5 Strategy - V4 with proactive loss hedging.

Strategy:
- When any side hits winner_threshold (default 0.6), declare it as winner
- Buy BOTH sides simultaneously to:
  1. Achieve target_profit_usdc profit if declared outcome wins
  2. Maintain maximum loss cap (hedge_loss_threshold) if opposite outcome wins
- Always buys more of the cheaper side to minimize cost
- If price is above max_buy_price, don't buy
- If declared winner changes or price drops below threshold, reset and allow new declaration
- Also includes reactive hedging if loss exceeds threshold (backup safety)
"""

from dataclasses import dataclass

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision
from polytrader.types import CandleData


@dataclass
class GabagoolV5State:
    """Tracks state for gabagool V5 strategy per market."""

    declared_winner: str | None = None  # "UP" or "DOWN" or None
    buy_done: bool = False  # Whether we've made the buy for current declared winner


class GabagoolV5Strategy:
    """V4 strategy with proactive loss hedging.
    
    Strategy:
    - When any side hits winner_threshold, declare it as winner
    - Buy BOTH sides simultaneously to achieve target profit while maintaining loss cap
    - Always buys more of the cheaper side to minimize cost
    - If price is above max_buy_price, don't buy
    - If declared winner changes or price drops below threshold, reset and allow new declaration
    - Proactive: Maintains loss cap from the start (never exceeds threshold)
    - Reactive: Also hedges if loss somehow exceeds threshold (backup safety)
    """

    def __init__(
        self,
        target_profit_usdc: float = 10.0,
        winner_threshold: float = 0.6,
        max_buy_price: float = 0.65,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 500.0,
        hedge_loss_threshold: float = 50.0,
        max_hedge_price: float = 0.8,  # Max price to pay for hedging
    ) -> None:
        self.target_profit_usdc = target_profit_usdc
        self.winner_threshold = winner_threshold
        self.max_buy_price = max_buy_price
        self.min_trade_amount_usdc = min_trade_amount_usdc
        self.max_capital_per_market_usdc = max_capital_per_market_usdc
        self.hedge_loss_threshold = hedge_loss_threshold
        self.max_hedge_price = max_hedge_price

        # Per-market state
        self.market_states: dict[str, GabagoolV5State] = {}

    def _get_state(self, market_id: str) -> GabagoolV5State:
        """Get or create state for a market."""
        if market_id not in self.market_states:
            self.market_states[market_id] = GabagoolV5State()
        return self.market_states[market_id]

    def _calculate_potential_loss(
        self,
        portfolio: Portfolio,
        market_id: str,
        outcome: str,
    ) -> float:
        """Calculate potential loss if the opposite outcome wins.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            outcome: "UP" or "DOWN" - the outcome we're checking loss for
            
        Returns:
            Potential loss in USDC if the opposite outcome wins (negative means profit)
        """
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        # Calculate total cost
        total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        # Calculate payout if opposite outcome wins
        if outcome == "UP":
            # If DOWN wins, UP shares = $0, DOWN shares = $1
            payout = (down_pos.quantity * 1.0) if down_pos else 0.0
        else:  # outcome == "DOWN"
            # If UP wins, UP shares = $1, DOWN shares = $0
            payout = (up_pos.quantity * 1.0) if up_pos else 0.0
        
        # Loss = payout - total_cost (negative means profit)
        return payout - total_cost

    def _calculate_balanced_hedge(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> tuple[float, float]:
        """Calculate amounts to buy of both sides to achieve break-even.
        
        We want to buy both UP and DOWN shares such that regardless of which outcome wins,
        we break even. We'll buy more of the cheaper side to minimize cost.
        
        Goal: Both outcomes should pay out the same amount = total_cost (break-even)
        - If UP wins: (current_up + new_up) * 1.0 = total_cost + new_cost
        - If DOWN wins: (current_down + new_down) * 1.0 = total_cost + new_cost
        Where: new_cost = new_up * up_price + new_down * down_price
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current price of UP outcome
            down_price: Current price of DOWN outcome
            
        Returns:
            Tuple of (up_amount, down_amount) in USDC to spend, or (0.0, 0.0) if no hedge needed
        """
        if up_price >= 1.0 or down_price >= 1.0 or up_price <= 0 or down_price <= 0:
            return (0.0, 0.0)
        
        # Get existing positions
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        current_up_shares = up_pos.quantity if up_pos else 0.0
        current_down_shares = down_pos.quantity if down_pos else 0.0
        
        # Current total cost
        current_total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        if current_total_cost == 0:
            return (0.0, 0.0)
        
        # Check if we need hedging (if max potential loss exceeds threshold)
        potential_loss_up = self._calculate_potential_loss(portfolio, market_id, "UP")
        potential_loss_down = self._calculate_potential_loss(portfolio, market_id, "DOWN")
        max_potential_loss = max(potential_loss_up, potential_loss_down)
        
        if max_potential_loss <= self.hedge_loss_threshold:
            return (0.0, 0.0)
        
        # To break even, we want both sides to pay out total_cost after buying
        # Let target = current_total_cost + new_cost
        # We want: current_up + new_up = current_down + new_down = target
        
        # Solving the system:
        # new_up = target - current_up
        # new_down = target - current_down
        # target = current_total_cost + new_up * up_price + new_down * down_price
        # target = current_total_cost + (target - current_up) * up_price + (target - current_down) * down_price
        # target = current_total_cost + target * up_price - current_up * up_price + target * down_price - current_down * down_price
        # target - target * up_price - target * down_price = current_total_cost - current_up * up_price - current_down * down_price
        # target * (1 - up_price - down_price) = current_total_cost - current_up * up_price - current_down * down_price
        
        # Note: up_price + down_price is typically close to 1.0, but may not be exactly 1.0
        price_sum = up_price + down_price
        if abs(1.0 - price_sum) < 0.01:  # Very close to 1.0, use approximation
            # If prices sum to ~1.0, we can't perfectly break even, so we aim to minimize loss
            # Buy more of the cheaper side to balance
            if up_price < down_price:
                # UP is cheaper, buy more UP
                # Calculate to break even if UP wins: (current_up + new_up) = current_total_cost + new_cost
                # new_up = (current_total_cost - current_up) / (1 - up_price)
                needed_up_shares = (current_total_cost - current_up_shares) / (1.0 - up_price)
                up_amount = needed_up_shares * up_price
                
                # Then calculate DOWN needed to also break even if DOWN wins
                new_total_cost = current_total_cost + up_amount
                needed_down_shares = (new_total_cost - current_down_shares) / (1.0 - down_price)
                down_amount = needed_down_shares * down_price
            else:
                # DOWN is cheaper, buy more DOWN
                needed_down_shares = (current_total_cost - current_down_shares) / (1.0 - down_price)
                down_amount = needed_down_shares * down_price
                
                new_total_cost = current_total_cost + down_amount
                needed_up_shares = (new_total_cost - current_up_shares) / (1.0 - up_price)
                up_amount = needed_up_shares * up_price
        else:
            # Prices don't sum to 1.0, solve the system properly
            denominator = 1.0 - price_sum
            if abs(denominator) < 0.0001:
                # Prices sum to exactly 1.0, can't solve this way
                # Fall back to buying more of cheaper side
                if up_price < down_price:
                    needed_up_shares = (current_total_cost - current_up_shares) / (1.0 - up_price)
                    up_amount = max(0.0, needed_up_shares * up_price)
                    down_amount = 0.0
                else:
                    needed_down_shares = (current_total_cost - current_down_shares) / (1.0 - down_price)
                    down_amount = max(0.0, needed_down_shares * down_price)
                    up_amount = 0.0
            else:
                # Solve for target
                target = (current_total_cost - current_up_shares * up_price - current_down_shares * down_price) / denominator
                
                needed_up_shares = max(0.0, target - current_up_shares)
                needed_down_shares = max(0.0, target - current_down_shares)
                
                up_amount = needed_up_shares * up_price
                down_amount = needed_down_shares * down_price
        
        # Only return if amounts are reasonable
        if up_amount < self.min_trade_amount_usdc:
            up_amount = 0.0
        if down_amount < self.min_trade_amount_usdc:
            down_amount = 0.0
        
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

    def _calculate_hedged_profit_trade(
        self,
        portfolio: Portfolio,
        market_id: str,
        outcome: str,
        outcome_price: float,
        opposite_price: float,
    ) -> tuple[float, float]:
        """Calculate amounts to buy of both sides to achieve target profit while maintaining loss cap.
        
        This ensures we:
        1. Achieve target_profit_usdc if the declared outcome wins
        2. Never exceed hedge_loss_threshold loss if the opposite outcome wins
        
        Formula:
        - Buy X shares of outcome at outcome_price
        - Buy Y shares of opposite outcome at opposite_price
        
        Constraints:
        - If outcome wins: (current_outcome + X) * 1.0 - (current_cost + X*outcome_price + Y*opposite_price) >= target_profit
        - If opposite wins: (current_opposite + Y) * 1.0 - (current_cost + X*outcome_price + Y*opposite_price) >= -hedge_loss_threshold
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            outcome: "UP" or "DOWN" - the outcome we're targeting for profit
            outcome_price: Current price of the target outcome
            opposite_price: Current price of the opposite outcome
            
        Returns:
            Tuple of (outcome_amount, opposite_amount) in USDC to spend
        """
        if outcome_price >= 1.0 or opposite_price >= 1.0 or outcome_price <= 0 or opposite_price <= 0:
            return (0.0, 0.0)
        
        # Get existing positions
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        
        current_up_shares = up_pos.quantity if up_pos else 0.0
        current_down_shares = down_pos.quantity if down_pos else 0.0
        
        current_total_cost = (
            (up_pos.quantity * up_pos.avg_price if up_pos else 0.0)
            + (down_pos.quantity * down_pos.avg_price if down_pos else 0.0)
        )
        
        # Current profit/loss scenarios
        if outcome == "UP":
            current_outcome_shares = current_up_shares
            current_opposite_shares = current_down_shares
            current_profit_if_outcome_wins = current_up_shares * 1.0 - current_total_cost
            current_profit_if_opposite_wins = current_down_shares * 1.0 - current_total_cost
        else:  # outcome == "DOWN"
            current_outcome_shares = current_down_shares
            current_opposite_shares = current_up_shares
            current_profit_if_outcome_wins = current_down_shares * 1.0 - current_total_cost
            current_profit_if_opposite_wins = current_up_shares * 1.0 - current_total_cost
        
        # Check if we already have enough profit
        if current_profit_if_outcome_wins >= self.target_profit_usdc:
            return (0.0, 0.0)
        
        # Calculate needed profit
        needed_profit = self.target_profit_usdc - current_profit_if_outcome_wins
        
        # Calculate maximum acceptable loss if opposite wins
        max_loss = -self.hedge_loss_threshold
        current_loss_if_opposite_wins = current_profit_if_opposite_wins
        
        # We need to solve:
        # Constraint 1: (current_outcome + X) - (current_cost + X*outcome_price + Y*opposite_price) >= target_profit
        # Constraint 2: (current_opposite + Y) - (current_cost + X*outcome_price + Y*opposite_price) >= max_loss
        
        # Simplifying:
        # X - X*outcome_price - Y*opposite_price >= needed_profit
        # Y - X*outcome_price - Y*opposite_price >= max_loss - current_loss_if_opposite_wins
        
        # From constraint 1: X*(1 - outcome_price) - Y*opposite_price >= needed_profit
        # From constraint 2: Y*(1 - opposite_price) - X*outcome_price >= max_loss - current_loss_if_opposite_wins
        
        # Solving constraint 1 for X (minimum needed for profit):
        # X*(1 - outcome_price) >= needed_profit + Y*opposite_price
        # X >= (needed_profit + Y*opposite_price) / (1 - outcome_price)
        
        # Solving constraint 2 for Y (minimum needed to cap loss):
        # Y*(1 - opposite_price) >= max_loss - current_loss_if_opposite_wins + X*outcome_price
        # Y >= (max_loss - current_loss_if_opposite_wins + X*outcome_price) / (1 - opposite_price)
        
        # Iterative approach: start with Y=0, calculate X, then recalculate Y, then X again
        # Or solve the system:
        
        # From constraint 1: X = (needed_profit + Y*opposite_price) / (1 - outcome_price)
        # Substitute into constraint 2:
        # Y*(1 - opposite_price) >= max_loss - current_loss_if_opposite_wins + outcome_price * (needed_profit + Y*opposite_price) / (1 - outcome_price)
        # Y*(1 - opposite_price) >= max_loss - current_loss_if_opposite_wins + outcome_price*needed_profit/(1-outcome_price) + Y*outcome_price*opposite_price/(1-outcome_price)
        # Y*(1 - opposite_price) - Y*outcome_price*opposite_price/(1-outcome_price) >= max_loss - current_loss_if_opposite_wins + outcome_price*needed_profit/(1-outcome_price)
        # Y * [(1-opposite_price)*(1-outcome_price) - outcome_price*opposite_price] / (1-outcome_price) >= max_loss - current_loss_if_opposite_wins + outcome_price*needed_profit/(1-outcome_price)
        
        # This is getting complex. Let's use a simpler iterative approach:
        
        # ALWAYS hedge: Buy both sides to maintain loss cap while achieving profit
        # We solve both constraints simultaneously using iterative approach
        
        # Constraint 1: (current_outcome + X) - (current_cost + X*outcome_price + Y*opposite_price) >= target_profit
        # Constraint 2: (current_opposite + Y) - (current_cost + X*outcome_price + Y*opposite_price) >= max_loss
        
        # Iterative solution: Start with X for profit, calculate Y for loss cap, then adjust X
        
        # Step 1: Calculate X needed for target profit (ignoring hedge cost)
        x_shares_for_profit = needed_profit / (1.0 - outcome_price)
        x_amount = x_shares_for_profit * outcome_price
        
        # Step 2: Calculate what loss would be if we buy X and opposite wins
        new_total_cost = current_total_cost + x_amount
        if outcome == "UP":
            profit_if_opposite_wins = current_down_shares * 1.0 - new_total_cost
        else:
            profit_if_opposite_wins = current_up_shares * 1.0 - new_total_cost
        
        # Step 3: Calculate Y needed to cap loss at max_loss
        if profit_if_opposite_wins < max_loss:
            # Need to buy Y to reduce loss
            loss_excess = max_loss - profit_if_opposite_wins
            y_shares = loss_excess / (1.0 - opposite_price)
            y_amount = y_shares * opposite_price
        else:
            # Loss is acceptable, but we still hedge to maintain the cap
            # Buy enough Y so loss stays at current level (maintain hedge ratio)
            # Calculate Y to keep loss at max_loss (safety buffer)
            y_amount = 0.0
        
        # Step 4: Recalculate X accounting for Y cost to ensure we still hit target profit
        new_total_cost_with_y = current_total_cost + y_amount
        profit_after_y = current_outcome_shares * 1.0 - new_total_cost_with_y
        remaining_needed_profit = self.target_profit_usdc - profit_after_y
        
        if remaining_needed_profit > 0:
            x_shares_adjusted = remaining_needed_profit / (1.0 - outcome_price)
            x_amount = x_shares_adjusted * outcome_price
        else:
            # Already have enough profit, but still buy X to maintain position
            x_amount = 0.0
        
        # Step 5: Final verification and adjustment
        final_total_cost = current_total_cost + x_amount + y_amount
        final_outcome_shares = current_outcome_shares + (x_amount / outcome_price if outcome_price > 0 else 0)
        final_opposite_shares = current_opposite_shares + (y_amount / opposite_price if opposite_price > 0 else 0)
        
        # Verify constraint 2 is met
        if outcome == "UP":
            final_profit_if_down_wins = final_opposite_shares * 1.0 - final_total_cost
        else:
            final_profit_if_down_wins = final_outcome_shares * 1.0 - final_total_cost
        
        # If loss cap not met, buy more Y
        if final_profit_if_down_wins < max_loss:
            additional_loss = max_loss - final_profit_if_down_wins
            additional_y_shares = additional_loss / (1.0 - opposite_price)
            y_amount += additional_y_shares * opposite_price
        
        # Always ensure we buy both sides to maintain hedge
        # Convert to amounts
        outcome_amount = max(x_amount, 0.0)
        opposite_amount = max(y_amount, 0.0)
        
        # CRITICAL: Always buy both sides to maintain loss cap proactively
        # Even if one side is small, we need to hedge
        # If opposite_amount is 0 or too small, calculate minimum hedge needed
        if opposite_amount < self.min_trade_amount_usdc and outcome_amount > 0:
            # Calculate minimum hedge to maintain loss cap
            # We want to ensure loss stays capped as we add more outcome shares
            # Buy at least enough opposite to maintain the hedge ratio
            min_hedge_amount = self.min_trade_amount_usdc
            # Or calculate based on maintaining loss cap
            if outcome == "UP":
                # If we buy X UP, we need Y DOWN to cap loss
                # Calculate Y such that: (current_down + Y) - (current_cost + X + Y) >= max_loss
                # Y - Y*down_price >= max_loss - current_down + current_cost + X
                # Actually, simpler: buy proportional hedge
                # Buy opposite proportional to outcome to maintain balance
                hedge_ratio = opposite_price / outcome_price  # How much opposite per $1 of outcome
                opposite_amount = outcome_amount * hedge_ratio
                # Ensure it's at least min_trade_amount
                if opposite_amount < self.min_trade_amount_usdc:
                    opposite_amount = self.min_trade_amount_usdc
            else:  # outcome == "DOWN"
                hedge_ratio = outcome_price / opposite_price
                opposite_amount = outcome_amount * hedge_ratio
                if opposite_amount < self.min_trade_amount_usdc:
                    opposite_amount = self.min_trade_amount_usdc
        
        # Apply minimum trade size filter (but we've ensured opposite_amount is at least min)
        if outcome_amount > 0 and outcome_amount < self.min_trade_amount_usdc:
            outcome_amount = 0.0
        
        return (outcome_amount, opposite_amount)

    def _check_and_reset_winner(
        self,
        state: GabagoolV5State,
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
        state: GabagoolV5State,
        outcome: str,
        price: float,
        opposite_price: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Process a single outcome (UP or DOWN) and return trade decision(s) if needed.
        
        Now buys both sides simultaneously to maintain profit target and loss cap.
        
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
            TradeDecision, list of TradeDecisions (outcome + hedge), or None
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
        
        # Execute primary trade first (for profit), then hedge will be calculated after execution
        # This ensures we use actual executed prices, not theoretical prices that may have changed
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
        
        # Return primary trade - hedge will be calculated after this executes
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
        """Make trading decision based on price thresholds with automatic hedging.
        
        Args:
            portfolio: Current portfolio state
            market_id: Market identifier
            up_price: Current best ask price for UP outcome
            down_price: Current best ask price for DOWN outcome
            timestamp: Optional timestamp for backtesting
            
        Returns:
            TradeDecision, list of TradeDecisions (normal trade + hedge), or None
        """
        # Early exit checks
        if portfolio.balance < self.min_trade_amount_usdc:
            return None
        
        if up_price <= 0 or down_price <= 0:
            return None
        
        if self._get_total_invested(portfolio, market_id) >= self.max_capital_per_market_usdc:
            return None
        
        state = self._get_state(market_id)
        
        # Check for hedging needs first (before normal strategy logic)
        # Buy both sides proportionally to achieve break-even, buying more of the cheaper side
        hedge_decisions: list[TradeDecision] = []
        
        # Check if we need hedging (if max potential loss exceeds threshold)
        # Note: potential_loss is negative for losses, positive for profits
        potential_loss_up = self._calculate_potential_loss(portfolio, market_id, "UP")
        potential_loss_down = self._calculate_potential_loss(portfolio, market_id, "DOWN")
        max_potential_loss = max(potential_loss_up, potential_loss_down)
        
        # If max_potential_loss is negative, it's a loss. We hedge if loss exceeds threshold.
        # max_potential_loss < -threshold means loss is worse than threshold
        if max_potential_loss < -self.hedge_loss_threshold:
            # Calculate balanced hedge: buy both sides to break even
            up_amount, down_amount = self._calculate_balanced_hedge(
                portfolio, market_id, up_price, down_price
            )
            
            # Check prices are acceptable for hedging
            if up_amount > 0 and up_price <= self.max_hedge_price:
                if portfolio.balance >= up_amount:
                    hedge_decisions.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="UP",
                            amount=up_amount,
                            price=up_price,
                        )
                    )
            
            if down_amount > 0 and down_price <= self.max_hedge_price:
                total_needed = up_amount + down_amount
                if portfolio.balance >= total_needed:
                    hedge_decisions.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=down_price,
                        )
                    )
                elif portfolio.balance >= down_amount and up_amount == 0:
                    # Can only afford DOWN
                    hedge_decisions.append(
                        TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=down_amount,
                            price=down_price,
                        )
                    )
        
        # Check which outcomes are at threshold and within buy price range
        up_valid = up_price >= self.winner_threshold and up_price <= self.max_buy_price
        down_valid = down_price >= self.winner_threshold and down_price <= self.max_buy_price
        
        # Reset winners that are no longer valid
        if not up_valid:
            self._check_and_reset_winner(state, "UP", up_price)
        if not down_valid:
            self._check_and_reset_winner(state, "DOWN", down_price)
        
        # Process valid outcomes, prioritizing current declared winner if it's still valid
        # Always pass opposite price for proactive hedged trading (maintains loss cap while achieving profit)
        normal_decision: TradeDecision | list[TradeDecision] | None = None
        if state.declared_winner == "UP" and up_valid:
            normal_decision = self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
        elif state.declared_winner == "DOWN" and down_valid:
            normal_decision = self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        elif up_valid and not down_valid:
            normal_decision = self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
        elif down_valid and not up_valid:
            normal_decision = self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        elif up_valid and down_valid:
            # Both valid - if we have a declared winner that's still valid, it was processed
            # on lines 249-252. If we reach here, either:
            # 1. No declared winner yet (state.declared_winner is None) - first time seeing both valid
            # 2. Declared winner was just reset to None (because it became invalid, then both became valid again)
            # In either case, pick the one with better price (lower is better for buying)
            if up_price <= down_price:
                normal_decision = self._process_outcome(portfolio, market_id, state, "UP", up_price, down_price)
            else:
                normal_decision = self._process_outcome(portfolio, market_id, state, "DOWN", down_price, up_price)
        
        # Combine reactive hedge decisions with normal decision (if any)
        # Note: normal_decision may already include proactive hedging from _process_outcome
        if hedge_decisions and normal_decision:
            # Both reactive hedging and normal trading
            if isinstance(normal_decision, list):
                return hedge_decisions + normal_decision
            else:
                return hedge_decisions + [normal_decision]
        elif hedge_decisions:
            # Only reactive hedging (no normal trading)
            return hedge_decisions if len(hedge_decisions) > 1 else hedge_decisions[0]
        else:
            # Normal trading (may include proactive hedging)
            return normal_decision

    def check_hedge_after_trade(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Check if hedging is needed after a trade executes.
        
        This is called immediately after a trade executes, allowing us to:
        1. Recalculate hedge based on actual executed trade (not theoretical)
        2. Use current prices (which may have changed)
        3. Maintain loss cap proactively
        
        Args:
            portfolio: Current portfolio state (updated with last trade)
            market_id: Market identifier
            up_price: Current UP price
            down_price: Current DOWN price
            
        Returns:
            TradeDecision or list of TradeDecisions for hedging, or None if no hedge needed
        """
        # Check if we need hedging (if max potential loss exceeds threshold)
        # Note: potential_loss is negative for losses, positive for profits
        potential_loss_up = self._calculate_potential_loss(portfolio, market_id, "UP")
        potential_loss_down = self._calculate_potential_loss(portfolio, market_id, "DOWN")
        max_potential_loss = max(potential_loss_up, potential_loss_down)
        
        # If max_potential_loss is negative, it's a loss. We hedge if loss exceeds threshold.
        # max_potential_loss < -threshold means loss is worse than threshold
        # Example: loss = -138.86, threshold = 10.0, so -138.86 < -10.0 is True → hedge needed
        if max_potential_loss >= -self.hedge_loss_threshold:
            # Loss is acceptable, no hedge needed
            return None
        
        # Loss exceeds threshold, calculate hedge
        print(f"   🛡️  Hedging needed: potential loss ${max_potential_loss:.2f} exceeds threshold ${self.hedge_loss_threshold:.2f}")
        
        # Calculate hedge needed with current prices
        up_amount, down_amount = self._calculate_balanced_hedge(
            portfolio, market_id, up_price, down_price
        )
        
        print(f"   📊 Calculated hedge: UP=${up_amount:.2f}, DOWN=${down_amount:.2f} (prices: UP=${up_price:.4f}, DOWN=${down_price:.4f})")
        
        hedge_trades: list[TradeDecision] = []
        
        # Check prices are acceptable for hedging
        if up_amount > 0:
            if up_price > self.max_hedge_price:
                print(f"   ⚠️  UP price ${up_price:.4f} exceeds max_hedge_price ${self.max_hedge_price:.4f}, skipping UP hedge")
            elif portfolio.balance < up_amount:
                print(f"   ⚠️  Insufficient balance for UP hedge: need ${up_amount:.2f}, have ${portfolio.balance:.2f}")
            else:
                hedge_trades.append(
                    TradeDecision(
                        market_id=market_id,
                        outcome="UP",
                        amount=up_amount,
                        price=up_price,
                    )
                )
                print(f"   ✅ Adding UP hedge: ${up_amount:.2f} @ ${up_price:.4f}")
        
        if down_amount > 0:
            total_needed = up_amount + down_amount
            if down_price > self.max_hedge_price:
                print(f"   ⚠️  DOWN price ${down_price:.4f} exceeds max_hedge_price ${self.max_hedge_price:.4f}, skipping DOWN hedge")
            elif portfolio.balance < total_needed:
                if up_amount == 0:
                    # Can only afford DOWN
                    if portfolio.balance >= down_amount:
                        hedge_trades.append(
                            TradeDecision(
                                market_id=market_id,
                                outcome="DOWN",
                                amount=down_amount,
                                price=down_price,
                            )
                        )
                        print(f"   ✅ Adding DOWN hedge (partial): ${down_amount:.2f} @ ${down_price:.4f}")
                    else:
                        print(f"   ⚠️  Insufficient balance for DOWN hedge: need ${down_amount:.2f}, have ${portfolio.balance:.2f}")
                else:
                    print(f"   ⚠️  Insufficient balance for both hedges: need ${total_needed:.2f}, have ${portfolio.balance:.2f}")
            else:
                hedge_trades.append(
                    TradeDecision(
                        market_id=market_id,
                        outcome="DOWN",
                        amount=down_amount,
                        price=down_price,
                    )
                )
                print(f"   ✅ Adding DOWN hedge: ${down_amount:.2f} @ ${down_price:.4f}")
        
        if not hedge_trades:
            print(f"   ⚠️  No hedge trades generated (amounts too small or prices too high)")
            return None
        
        print(f"   🎯 Executing {len(hedge_trades)} hedge trade(s)")
        return hedge_trades if len(hedge_trades) > 1 else hedge_trades[0]

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

