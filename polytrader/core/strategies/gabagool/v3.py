"""Gabagool V3 Strategy - Rebalancing continuous buying strategy.

Strategy:
- Every X seconds, buy both sides
- Always buy at least min_shares_per_trade total shares
- Distribute shares to maintain share_ratio between confident and less confident sides
- Rebalance portfolio to maintain target ratio over time
"""

import time
from dataclasses import dataclass, field

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision


@dataclass
class GabagoolV3State:
    """Tracks state for gabagool V3 strategy per market."""

    qty_yes: float = 0.0
    cost_yes: float = 0.0
    qty_no: float = 0.0
    cost_no: float = 0.0
    last_trade_time: float = 0.0
    pending_outcomes: set[str] = field(default_factory=set)  # Track which outcomes have pending trades


class GabagoolV3Strategy:
    """Rebalancing continuous buying strategy that maintains share_ratio.
    
    Strategy:
    - Every seconds_between_trades seconds, buy both sides
    - Always buy at least min_shares_per_trade total shares
    - Distribute shares to maintain share_ratio where CONFIDENT side has MORE shares
      Example: If share_ratio = 1.3, confident side has 1.3x the shares of less confident side
      Formula: confident_qty / less_confident_qty = share_ratio
    - If prices are equal (50/50), buy 50/50
    - If prices differ (e.g., 65/35), rebalance to maintain target ratio
    - HANDLES PRICE FLIPS: If confident side swaps (e.g., UP was confident, now DOWN is),
      the strategy automatically rebalances to maintain the ratio with the new confident side
    """

    def __init__(
        self,
        seconds_between_trades: float = 30.0,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 150.0,
        min_shares_per_trade: float = 10.0,
        share_ratio: float = 1.4,
        max_buy_price: float = 0.8,
        price_equality_threshold: float = 0.01,
    ) -> None:
        self.seconds_between_trades = seconds_between_trades
        self.min_trade_amount_usdc = min_trade_amount_usdc
        self.max_capital_per_market_usdc = max_capital_per_market_usdc
        self.min_shares_per_trade = min_shares_per_trade
        self.share_ratio = share_ratio
        self.max_buy_price = max_buy_price
        self.price_equality_threshold = price_equality_threshold

        # Per-market state
        self.market_states: dict[str, GabagoolV3State] = {}

    def _get_state(self, market_id: str) -> GabagoolV3State:
        """Get or create state for a market."""
        if market_id not in self.market_states:
            self.market_states[market_id] = GabagoolV3State()
        return self.market_states[market_id]

    def _sync_state(self, state: GabagoolV3State, portfolio: Portfolio, market_id: str) -> None:
        """Atomic state update from portfolio snapshot."""
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")

        state.qty_yes = up_pos.quantity if up_pos else 0.0
        state.cost_yes = (up_pos.quantity * up_pos.avg_price) if up_pos else 0.0
        state.qty_no = down_pos.quantity if down_pos else 0.0
        state.cost_no = (down_pos.quantity * down_pos.avg_price) if down_pos else 0.0

    def _determine_confident_side(
        self, up_price: float, down_price: float
    ) -> tuple[str, str, float, float, bool]:
        """Determine which side is more confident (higher price = more confident).
        
        Returns:
            (confident_side, less_confident_side, confident_price, less_confident_price, prices_equal)
        """
        if abs(up_price - down_price) < self.price_equality_threshold:
            # Prices are effectively equal, no confident side
            return "UP", "DOWN", up_price, down_price, True
        elif up_price > down_price:
            return "UP", "DOWN", up_price, down_price, False
        else:
            return "DOWN", "UP", down_price, up_price, False

    def _ensure_minimum_amount(
        self, shares: float, price: float, outcome: str
    ) -> tuple[float, float]:
        """Ensure trade amount meets minimum requirement by scaling up shares if needed.
        
        Args:
            shares: Number of shares to buy
            price: Price per share
            outcome: Outcome name (for error messages)
            
        Returns:
            Tuple of (adjusted_shares, adjusted_amount)
        """
        amount = shares * price
        
        if amount < self.min_trade_amount_usdc:
            # Scale up shares to meet minimum
            min_shares = self.min_trade_amount_usdc / price if price > 0 else shares
            adjusted_amount = min_shares * price
            return min_shares, adjusted_amount
        
        return shares, amount

    def _calculate_rebalancing_shares(
        self,
        confident_qty: float,
        less_confident_qty: float,
        confident_price: float,
        less_confident_price: float,
        total_shares_to_buy: float,
        prices_equal: bool,
    ) -> tuple[float, float]:
        """Calculate how many shares to buy for each side to rebalance toward target ratio.
        
        Args:
            confident_qty: Current quantity of confident side
            less_confident_qty: Current quantity of less confident side
            confident_price: Price of confident side
            less_confident_price: Price of less confident side
            total_shares_to_buy: Minimum total shares to buy (min_shares_per_trade)
            prices_equal: Whether prices are equal (buy 50/50)
            
        Returns:
            (confident_shares_to_buy, less_confident_shares_to_buy)
        """
        # If prices are equal, buy 50/50
        if prices_equal:
            confident_shares = total_shares_to_buy / 2.0
            less_confident_shares = total_shares_to_buy / 2.0
            return confident_shares, less_confident_shares
        
        target_ratio = self.share_ratio
        
        # Handle edge cases
        if confident_qty == 0 and less_confident_qty == 0:
            # No positions: distribute according to target ratio
            # Confident side gets MORE shares (target_ratio times more)
            # Example: ratio=1.3, buy 10 shares -> confident gets 5.65, less_confident gets 4.35
            confident_shares = total_shares_to_buy * target_ratio / (target_ratio + 1)
            less_confident_shares = total_shares_to_buy / (target_ratio + 1)
        elif confident_qty > 0 and less_confident_qty == 0:
            # Only have confident side: distribute according to target ratio
            # After this trade, we want ratio to approach target
            # For now, just buy proportionally to establish the other side
            confident_shares = total_shares_to_buy * target_ratio / (target_ratio + 1)
            less_confident_shares = total_shares_to_buy / (target_ratio + 1)
        elif confident_qty == 0 and less_confident_qty > 0:
            # Only have less_confident side: distribute according to target ratio
            # After this trade, we want ratio to approach target
            confident_shares = total_shares_to_buy * target_ratio / (target_ratio + 1)
            less_confident_shares = total_shares_to_buy / (target_ratio + 1)
        else:
            # Both sides exist: calculate to rebalance toward target ratio
            # IMPORTANT: This handles price flips/swaps - if confident side changed, the quantities
            # will be mapped differently (confident_qty might now be the old less_confident_qty)
            # and we'll buy to rebalance toward the target ratio with the NEW confident side
            # We want: (confident_qty + confident_buy) / (less_confident_qty + less_confident_buy) = target_ratio
            # This ensures confident side always has MORE shares (target_ratio times more)
            # And: confident_buy + less_confident_buy = total_shares_to_buy
            # Solving: (confident_qty + c) / (less_confident_qty + total_shares_to_buy - c) = target_ratio
            # confident_qty + c = target_ratio * (less_confident_qty + total_shares_to_buy - c)
            # confident_qty + c = target_ratio * less_confident_qty + target_ratio * total_shares_to_buy - target_ratio * c
            # c + target_ratio * c = target_ratio * less_confident_qty + target_ratio * total_shares_to_buy - confident_qty
            # c * (1 + target_ratio) = target_ratio * less_confident_qty + target_ratio * total_shares_to_buy - confident_qty
            # c = (target_ratio * less_confident_qty + target_ratio * total_shares_to_buy - confident_qty) / (1 + target_ratio)
            
            numerator = target_ratio * less_confident_qty + target_ratio * total_shares_to_buy - confident_qty
            confident_shares = numerator / (1 + target_ratio)
            less_confident_shares = total_shares_to_buy - confident_shares
            
            # Ensure non-negative
            confident_shares = max(0.0, confident_shares)
            less_confident_shares = max(0.0, less_confident_shares)
            
            # If one side is negative or sum doesn't match, redistribute proportionally
            # This can happen when portfolio is very far from target (e.g., after price swap)
            # In that case, we buy according to target ratio to move toward it
            if confident_shares < 0 or less_confident_shares < 0 or abs((confident_shares + less_confident_shares) - total_shares_to_buy) > 0.001:
                confident_shares = total_shares_to_buy * target_ratio / (target_ratio + 1)
                less_confident_shares = total_shares_to_buy / (target_ratio + 1)
        
        return confident_shares, less_confident_shares

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make trading decision: buy both sides to maintain share_ratio."""
        now = timestamp if timestamp is not None else time.time()
        state = self._get_state(market_id)
        self._sync_state(state, portfolio, market_id)

        # Early exit checks
        if portfolio.balance < self.min_trade_amount_usdc:
            return None

        total_invested = state.cost_yes + state.cost_no
        if total_invested >= self.max_capital_per_market_usdc:
            return None

        # If we have pending trades, wait for them to complete before making new decisions
        if state.pending_outcomes:
            return None

        # Rate limiting - check time since last completed trade
        if state.last_trade_time > 0:
            elapsed = now - state.last_trade_time
            if elapsed < self.seconds_between_trades:
                return None

        # Validate prices
        if up_price <= 0 or down_price <= 0:
            return None

        # Don't trade if either price is at or above max_buy_price
        if up_price >= self.max_buy_price or down_price >= self.max_buy_price:
            return None

        # Determine confident and less confident sides
        # Note: This is recalculated each trade, so if prices swap (e.g., UP was confident
        # but now DOWN is confident), we will properly rebalance to maintain the target ratio
        confident_side, less_confident_side, confident_price, less_confident_price, prices_equal = (
            self._determine_confident_side(up_price, down_price)
        )

        # Get current quantities based on which side is currently confident
        # This mapping ensures we rebalance correctly even if prices have swapped
        if confident_side == "UP":
            confident_qty = state.qty_yes
            less_confident_qty = state.qty_no
        else:
            confident_qty = state.qty_no
            less_confident_qty = state.qty_yes

        # Calculate shares to buy to rebalance toward target ratio
        confident_shares, less_confident_shares = self._calculate_rebalancing_shares(
            confident_qty=confident_qty,
            less_confident_qty=less_confident_qty,
            confident_price=confident_price,
            less_confident_price=less_confident_price,
            total_shares_to_buy=self.min_shares_per_trade,
            prices_equal=prices_equal,
        )

        # Ensure both trades meet minimum amount requirement
        less_confident_shares, less_confident_amount = self._ensure_minimum_amount(
            less_confident_shares, less_confident_price, less_confident_side
        )
        confident_shares, confident_amount = self._ensure_minimum_amount(
            confident_shares, confident_price, confident_side
        )

        # Check if we have enough balance for both trades
        total_needed = less_confident_amount + confident_amount
        if portfolio.balance < total_needed:
            return None

        # Track pending trades
        state.pending_outcomes = {less_confident_side, confident_side}

        return [
            TradeDecision(
                market_id=market_id,
                outcome=less_confident_side,
                amount=less_confident_amount,
                price=less_confident_price,
            ),
            TradeDecision(
                market_id=market_id,
                outcome=confident_side,
                amount=confident_amount,
                price=confident_price,
            ),
        ]

    def on_trade_executed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called after a trade is successfully executed."""
        state = self._get_state(market_id)

        # Remove this outcome from pending set
        state.pending_outcomes.discard(outcome)

        # Only update last_trade_time if all pending trades are complete
        if not state.pending_outcomes:
            now = timestamp if timestamp is not None else time.time()
            state.last_trade_time = now

    def on_trade_failed(
        self,
        market_id: str,
        outcome: str,
        price: float,
        timestamp: float | None = None,
    ) -> None:
        """Called when a trade execution fails."""
        state = self._get_state(market_id)

        # Remove this outcome from pending set
        state.pending_outcomes.discard(outcome)

        # If all trades completed (some succeeded, some failed), reset to allow retry
        # This prevents getting stuck if one trade in a pair fails
        if not state.pending_outcomes:
            # Reset last_trade_time to allow immediate retry
            # The strategy will re-evaluate on next decide() call based on portfolio state
            state.last_trade_time = 0.0
