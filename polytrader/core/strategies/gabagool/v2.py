"""Gabagool V2 Strategy - Continuous buying strategy.

Strategy:
- Every X seconds, buy both sides
- Ensure less confident side (if it wins) is break-even or small loss
- Ensure more confident side maintains profit
- Each trade must be profitable for the more expensive/confident side
"""

import time
from dataclasses import dataclass, field

from polytrader.core.portfolio import Portfolio
from polytrader.core.trade import TradeDecision


@dataclass
class GabagoolV2State:
    """Tracks state for gabagool V2 strategy per market."""

    qty_yes: float = 0.0
    cost_yes: float = 0.0
    qty_no: float = 0.0
    cost_no: float = 0.0
    last_trade_time: float = 0.0
    pending_outcomes: set[str] = field(default_factory=set)  # Track which outcomes have pending trades


class GabagoolV2Strategy:
    """Continuous buying strategy that maintains break-even on less confident side.
    
    Strategy:
    - Every seconds_between_trades seconds, buy both sides
    - Buy in a way that less confident side (if it wins) is break-even or small loss
    - More confident side maintains profit
    - Each trade must be profitable for the more expensive/confident side
    """

    def __init__(
        self,
        seconds_between_trades: float = 30.0,
        min_trade_amount_usdc: float = 1.0,
        max_capital_per_market_usdc: float = 150.0,
        max_shares_per_trade: float = 10.0,
        share_ratio: float = 0.5,
        max_buy_price: float = 0.8,
    ) -> None:
        self.seconds_between_trades = seconds_between_trades
        self.min_trade_amount_usdc = min_trade_amount_usdc
        self.max_capital_per_market_usdc = max_capital_per_market_usdc
        self.max_shares_per_trade = max_shares_per_trade
        self.share_ratio = share_ratio
        self.max_buy_price = max_buy_price

        # Per-market state
        self.market_states: dict[str, GabagoolV2State] = {}

    def _get_state(self, market_id: str) -> GabagoolV2State:
        """Get or create state for a market."""
        if market_id not in self.market_states:
            self.market_states[market_id] = GabagoolV2State()
        return self.market_states[market_id]

    def _sync_state(self, state: GabagoolV2State, portfolio: Portfolio, market_id: str) -> None:
        """Atomic state update from portfolio snapshot."""
        up_pos = portfolio.get_position(market_id, "UP")
        down_pos = portfolio.get_position(market_id, "DOWN")

        state.qty_yes = up_pos.quantity if up_pos else 0.0
        state.cost_yes = (up_pos.quantity * up_pos.avg_price) if up_pos else 0.0
        state.qty_no = down_pos.quantity if down_pos else 0.0
        state.cost_no = (down_pos.quantity * down_pos.avg_price) if down_pos else 0.0

    def _determine_confident_side(
        self, up_price: float, down_price: float
    ) -> tuple[str, str, float, float]:
        """Determine which side is more confident (higher price = more confident)."""
        if up_price >= down_price:
            return "UP", "DOWN", up_price, down_price
        else:
            return "DOWN", "UP", down_price, up_price

    def _calculate_shares(self, confident_shares: float) -> tuple[float, float]:
        """Calculate shares for confident and less confident sides."""
        confident = confident_shares * (self.share_ratio / (self.share_ratio + 1))
        less_confident = confident_shares * (1 / (self.share_ratio + 1))
        return confident, less_confident

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

    def decide(
        self,
        portfolio: Portfolio,
        market_id: str,
        up_price: float,
        down_price: float,
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Make trading decision: buy both sides to maintain break-even on less confident side."""
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
        confident_side, less_confident_side, confident_price, less_confident_price = (
            self._determine_confident_side(up_price, down_price)
        )

        # Case 1: No positions - buy both sides proportionally
        if state.qty_yes == 0 and state.qty_no == 0:
            confident_shares, less_confident_shares = self._calculate_shares(
                self.max_shares_per_trade
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

        # Case 2: Only have NO shares - buy YES to balance
        elif state.qty_yes == 0 and state.qty_no > 0:
            no_avg_price = state.cost_no / state.qty_no if state.qty_no > 0 else 0.0

            # Calculate shares to buy based on existing NO position
            # If NO was bought at higher price, buy more YES to balance
            if no_avg_price > up_price:
                shares = state.qty_no / self.share_ratio
            else:
                shares = state.qty_no * self.share_ratio

            # Ensure trade meets minimum amount requirement
            shares, amount = self._ensure_minimum_amount(shares, up_price, "UP")

            # Check if we have enough balance
            if portfolio.balance < amount:
                return None

            # Track pending trade
            state.pending_outcomes = {"UP"}

            return TradeDecision(
                market_id=market_id,
                outcome="UP",
                amount=amount,
                price=up_price,
            )

        # Case 3: Only have YES shares - buy NO to balance
        elif state.qty_no == 0 and state.qty_yes > 0:
            yes_avg_price = state.cost_yes / state.qty_yes if state.qty_yes > 0 else 0.0

            # Calculate shares to buy based on existing YES position
            # If YES was bought at higher price, buy more NO to balance
            if yes_avg_price > down_price:
                shares = state.qty_yes / self.share_ratio
            else:
                shares = state.qty_yes * self.share_ratio

            # Ensure trade meets minimum amount requirement
            shares, amount = self._ensure_minimum_amount(shares, down_price, "DOWN")

            # Check if we have enough balance
            if portfolio.balance < amount:
                return None

            # Track pending trade
            state.pending_outcomes = {"DOWN"}

            return TradeDecision(
                market_id=market_id,
                outcome="DOWN",
                amount=amount,
                price=down_price,
            )

        # Case 4: Have both sides - continue buying both proportionally
        else:
            confident_shares, less_confident_shares = self._calculate_shares(
                self.max_shares_per_trade
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
