"""Gabagool V4 Strategy - Winner at 0.6 with profit targeting.

Strategy:
- When any side hits 0.6, declare it as winner and buy enough to have X$ profit
- If the other side hits 0.6 and keeps it for 1 minute, buy enough of that side to have X$ profit
"""

import time
from dataclasses import dataclass, field

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision


@dataclass
class GabagoolV4State:
    """Tracks state for gabagool V4 strategy per market."""

    declared_winner: str | None = None  # "UP" or "DOWN" or None
    initial_buy_done: bool = False  # Whether we've made the initial buy for declared winner
    other_side_hit_0_6_time: float | None = None  # Timestamp when other side first hit 0.6
    other_side_buy_done: bool = False  # Whether we've bought the other side


class GabagoolV4Strategy:
    """Strategy that buys the declared winner at 0.6 and hedges if other side hits 0.6 for 1 minute.
    
    Strategy:
    - When any side hits 0.6, declare it as winner
    - Buy enough of that side to have target_profit_usdc profit if it wins
    - If the other side hits 0.6 and stays there for 1 minute (60 seconds), 
      buy enough of that side to have target_profit_usdc profit if it wins
    """

    def __init__(
        self,
        target_profit_usdc: float = 10.0,
        winner_threshold: float = 0.6,
        other_side_hold_duration_seconds: float = 60.0,
        max_buy_price: float = 0.65,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 500.0,
    ) -> None:
        self.target_profit_usdc = target_profit_usdc
        self.winner_threshold = winner_threshold
        self.other_side_hold_duration_seconds = other_side_hold_duration_seconds
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

    def _calculate_amount_for_profit(self, price: float, target_profit: float) -> float:
        """Calculate amount (USDC) to spend to achieve target profit if outcome wins.
        
        If we buy shares at price P and outcome wins (price = 1.0):
        - Cost = shares * P
        - Value when wins = shares * 1.0 = shares
        - Profit = shares - shares * P = shares * (1 - P)
        
        To get profit = target_profit:
        - shares = target_profit / (1 - P)
        - amount = shares * P = target_profit * P / (1 - P)
        
        Args:
            price: Current price of the outcome
            target_profit: Desired profit in USDC if outcome wins
            
        Returns:
            Amount in USDC to spend
        """
        if price >= 1.0:
            # Can't achieve profit if price is already 1.0
            return 0.0
        if price <= 0:
            return 0.0
        
        return target_profit * price / (1.0 - price)

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make trading decision based on price thresholds."""
        now = timestamp if timestamp is not None else time.time()
        state = self._get_state(market_id)

        # Early exit checks
        if portfolio.balance < self.min_trade_amount_usdc:
            return None

        # Validate prices
        if up_price <= 0 or down_price <= 0:
            return None

        # Check total capital invested in this market
        total_invested = 0.0
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")
        if up_pos:
            total_invested += up_pos.quantity * up_pos.avg_price
        if down_pos:
            total_invested += down_pos.quantity * down_pos.avg_price
        
        if total_invested >= self.max_capital_per_market_usdc:
            return None

        # Check if UP hits winner threshold
        if up_price >= self.winner_threshold:
            # If no winner declared yet, declare UP as winner
            if state.declared_winner is None:
                state.declared_winner = "UP"
                state.initial_buy_done = False
                state.other_side_hit_0_6_time = None
                state.other_side_buy_done = False
            
            # If UP is declared winner and we haven't made initial buy
            if state.declared_winner == "UP" and not state.initial_buy_done:
                if up_price > self.max_buy_price:
                    return None  # Price too high
                
                amount = self._calculate_amount_for_profit(up_price, self.target_profit_usdc)
                if amount < self.min_trade_amount_usdc:
                    amount = self.min_trade_amount_usdc
                
                if portfolio.balance < amount:
                    return None
                
                state.initial_buy_done = True
                return TradeDecision(
                    market_id=market_id,
                    outcome="UP",
                    amount=amount,
                    price=up_price,
                )
            
            # If DOWN was declared winner and UP (other side) hits 0.6
            if state.declared_winner == "DOWN":
                # Check if this is the first time other side hit 0.6
                if state.other_side_hit_0_6_time is None:
                    state.other_side_hit_0_6_time = now
                
                # Check if other side has been at 0.6+ for required duration
                if not state.other_side_buy_done:
                    elapsed = now - state.other_side_hit_0_6_time
                    if elapsed >= self.other_side_hold_duration_seconds:
                        if up_price > self.max_buy_price:
                            return None  # Price too high
                        
                        amount = self._calculate_amount_for_profit(up_price, self.target_profit_usdc)
                        if amount < self.min_trade_amount_usdc:
                            amount = self.min_trade_amount_usdc
                        
                        if portfolio.balance < amount:
                            return None
                        
                        state.other_side_buy_done = True
                        return TradeDecision(
                            market_id=market_id,
                            outcome="UP",
                            amount=amount,
                            price=up_price,
                        )
        else:
            # UP is below threshold - if it was the other side being tracked, reset timer
            if state.declared_winner == "DOWN" and state.other_side_hit_0_6_time is not None:
                state.other_side_hit_0_6_time = None
        
        # Check if DOWN hits winner threshold
        if down_price >= self.winner_threshold:
            # If no winner declared yet, declare DOWN as winner
            if state.declared_winner is None:
                state.declared_winner = "DOWN"
                state.initial_buy_done = False
                state.other_side_hit_0_6_time = None
                state.other_side_buy_done = False
            
            # If DOWN is declared winner and we haven't made initial buy
            if state.declared_winner == "DOWN" and not state.initial_buy_done:
                if down_price > self.max_buy_price:
                    return None  # Price too high
                
                amount = self._calculate_amount_for_profit(down_price, self.target_profit_usdc)
                if amount < self.min_trade_amount_usdc:
                    amount = self.min_trade_amount_usdc
                
                if portfolio.balance < amount:
                    return None
                
                state.initial_buy_done = True
                return TradeDecision(
                    market_id=market_id,
                    outcome="DOWN",
                    amount=amount,
                    price=down_price,
                )
            
            # If UP was declared winner and DOWN (other side) hits 0.6
            if state.declared_winner == "UP":
                # Check if this is the first time other side hit 0.6
                if state.other_side_hit_0_6_time is None:
                    state.other_side_hit_0_6_time = now
                
                # Check if other side has been at 0.6+ for required duration
                if not state.other_side_buy_done:
                    elapsed = now - state.other_side_hit_0_6_time
                    if elapsed >= self.other_side_hold_duration_seconds:
                        if down_price > self.max_buy_price:
                            return None  # Price too high
                        
                        amount = self._calculate_amount_for_profit(down_price, self.target_profit_usdc)
                        if amount < self.min_trade_amount_usdc:
                            amount = self.min_trade_amount_usdc
                        
                        if portfolio.balance < amount:
                            return None
                        
                        state.other_side_buy_done = True
                        return TradeDecision(
                            market_id=market_id,
                            outcome="DOWN",
                            amount=amount,
                            price=down_price,
                        )
        else:
            # DOWN is below threshold - if it was the other side being tracked, reset timer
            if state.declared_winner == "UP" and state.other_side_hit_0_6_time is not None:
                state.other_side_hit_0_6_time = None

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
        
        # Reset the buy flags to allow retry
        if state.declared_winner == outcome and state.initial_buy_done:
            state.initial_buy_done = False
        elif state.declared_winner is not None and state.declared_winner != outcome:
            if state.other_side_buy_done:
                state.other_side_buy_done = False
                state.other_side_hit_0_6_time = None  # Reset timer to allow retry

