"""Trading strategy protocol and implementations."""

import time
from dataclasses import dataclass
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


# ============================================================================
# Gabagool Strategy (Asymmetric Hedge)
# ============================================================================


@dataclass
class GabagoolState:
    """Tracks state for gabagool strategy per market."""

    qty_yes: float = 0.0
    cost_yes: float = 0.0
    qty_no: float = 0.0
    cost_no: float = 0.0
    last_trade_time_up: float = 0.0  # Last trade time for UP side
    last_trade_time_down: float = 0.0  # Last trade time for DOWN side
    last_trade_price: float = 0.0  # Last price we traded at
    last_trade_outcome: str = ""  # Last outcome we traded ("UP" or "DOWN")
    trade_count: int = 0
    locked_profit: bool = False  # True when profit is mathematically locked
    
    def get_last_trade_time(self, outcome: str) -> float:
        """Get last trade time for a specific outcome."""
        if outcome == "UP":
            return self.last_trade_time_up
        elif outcome == "DOWN":
            return self.last_trade_time_down
        return 0.0
    
    def set_last_trade_time(self, outcome: str, time: float) -> None:
        """Set last trade time for a specific outcome."""
        if outcome == "UP":
            self.last_trade_time_up = time
        elif outcome == "DOWN":
            self.last_trade_time_down = time


class GabagoolStrategy:
    """Asymmetric hedge strategy with arbitrage detection.
    
    Strategy:
    1. Check for arbitrage: if one side avg ~0.6 and other side is 0.15-0.16, buy to match
    2. Buy whichever side hits 0.6 first (at actual price if < 0.62)
    3. Buy the other side when it hits 0.35 or lower
    4. Keep accumulating until hedged: loss <= $5 OR profit > $5
    5. Limit accumulation: max 2.5x ratio between sides (based on share count)
    """

    def __init__(
            self,
            accumulate_price: float = 0.6,
            hedge_price: float = 0.35,
            max_accumulate_price: float = 0.62,
            max_buy_price: float = 0.92,
            max_ratio: float = 2.5,
            min_arbitrage_pair_cost: float = 0.95,
            max_order_size: float = 500.0,
            min_trade_size: float = 5.0,
            min_seconds_between_trades: float = 0.5,
            max_capital_per_market: float = 1000.0,
            max_loss_threshold: float = 5.0,
            lock_profit_threshold: float = 5.0,
    ) -> None:
            """Initialize asymmetric hedge strategy.

            Args:
                accumulate_price: Buy whichever side hits this price first (default 0.6)
                hedge_price: Buy the other side when it hits this or lower (default 0.35)
                max_accumulate_price: Maximum price to buy at when accumulating (default 0.62)
                max_buy_price: Maximum price to ever buy at, rejects prices >= this (default 0.92)
                max_ratio: Maximum ratio between sides based on SHARE COUNT (default 2.5)
                min_arbitrage_pair_cost: AVG_A + AVG_B must be < this for arbitrage (default 0.95)
                max_order_size: Maximum shares to buy in one operation
                min_trade_size: Minimum trade size in USDC
                min_seconds_between_trades: Minimum seconds between trades
                max_capital_per_market: Maximum capital per market
                max_loss_threshold: Maximum acceptable loss in USDC (default 5.0)
                lock_profit_threshold: Lock profit when profit exceeds this threshold in USDC (default 5.0)
            """
            self.accumulate_price = accumulate_price
            self.hedge_price = hedge_price
            self.max_accumulate_price = max_accumulate_price
            self.max_buy_price = max_buy_price
            self.max_ratio = max_ratio
            self.min_arbitrage_pair_cost = min_arbitrage_pair_cost
            self.max_order_size = max_order_size
            self.min_trade_size = min_trade_size
            self.min_seconds_between_trades = min_seconds_between_trades
            self.max_capital_per_market = max_capital_per_market
            self.max_loss_threshold = max_loss_threshold
            self.lock_profit_threshold = lock_profit_threshold

            self.market_states: dict[str, GabagoolState] = {}

    def __str__(self) -> str:
            return (
                f"GabagoolStrategy("
                f"accumulate@{self.accumulate_price:.2f}, "
                f"max_accumulate@{self.max_accumulate_price:.2f}, "
                f"max_buy@{self.max_buy_price:.2f}, "
                f"hedge@{self.hedge_price:.2f}, "
                f"max_ratio@{self.max_ratio:.1f}x, "
                f"max_loss=${self.max_loss_threshold:.1f})"
            )

    def _get_state(self, market_id: str) -> GabagoolState:
            """Get or create state for a market."""
            if market_id not in self.market_states:
                self.market_states[market_id] = GabagoolState()
            return self.market_states[market_id]
    
    def on_trade_executed(
            self,
            market_id: str,
            outcome: str,
            price: float,
            timestamp: float | None = None,
    ) -> None:
            """Called after a trade is successfully executed.
            
            Updates rate limiting state only when trades actually succeed.
            """
            now = timestamp if timestamp is not None else time.time()
            state = self._get_state(market_id)
            state.set_last_trade_time(outcome, now)
            state.last_trade_price = price
            state.last_trade_outcome = outcome
            state.trade_count += 1

    @staticmethod
    def _avg(cost: float, qty: float) -> float:
            """Calculate average price."""
            return cost / qty if qty > 0 else float("inf")

    def _pair_cost(
            self, cost_yes: float, qty_yes: float, cost_no: float, qty_no: float
    ) -> float:
            """Calculate pair cost: avg_YES + avg_NO."""
            avg_yes = self._avg(cost_yes, qty_yes)
            avg_no = self._avg(cost_no, qty_no)
            return avg_yes + avg_no

    def _get_current_state_from_portfolio(
            self, portfolio: Portfolio, market_id: str
    ) -> tuple[float, float, float, float]:
            """Get current state from portfolio positions.
            
            Returns:
                (qty_yes, cost_yes, qty_no, cost_no)
            """
            up_pos = portfolio.get_position(market_id, "UP")
            down_pos = portfolio.get_position(market_id, "DOWN")

            qty_yes = up_pos.quantity if up_pos else 0.0
            cost_yes = (up_pos.quantity * up_pos.avg_price) if up_pos else 0.0

            qty_no = down_pos.quantity if down_pos else 0.0
            cost_no = (down_pos.quantity * down_pos.avg_price) if down_pos else 0.0

            return qty_yes, cost_yes, qty_no, cost_no

    def _update_state_from_portfolio(
            self, portfolio: Portfolio, market_id: str, state: GabagoolState
    ) -> None:
            """Update strategy state from portfolio positions."""
            qty_yes, cost_yes, qty_no, cost_no = self._get_current_state_from_portfolio(
                portfolio, market_id
            )
            state.qty_yes = qty_yes
            state.cost_yes = cost_yes
            state.qty_no = qty_no
            state.cost_no = cost_no

            # Check if profit is locked (worst case scenario)
            # Always calculate profit as worst case: min_payout - total_cost
            # Only stop if profit > threshold (we've maximized profit enough)
            # Also check if we have arbitrage (matching shares with profitable pair cost)
            if qty_yes > 0 and qty_no > 0:
                min_payout = min(qty_yes, qty_no)  # Worst case: we get min of both sides
                total_cost = cost_yes + cost_no
                current_loss = total_cost - min_payout  # Worst case loss
                current_profit = min_payout - total_cost  # Worst case profit
                
                # Check if we have arbitrage: matching shares with profitable pair cost
                avg_yes = self._avg(cost_yes, qty_yes)
                avg_no = self._avg(cost_no, qty_no)
                pair_cost = avg_yes + avg_no
                
                # If shares are matching (within 5% difference) and pair cost is profitable, lock arbitrage
                shares_match = abs(qty_yes - qty_no) / max(qty_yes, qty_no) < 0.05 if max(qty_yes, qty_no) > 0 else False
                is_arbitrage = shares_match and pair_cost <= self.min_arbitrage_pair_cost
                
                # Lock if: profit exceeds lock_profit_threshold OR we have arbitrage
                state.locked_profit = current_profit > self.lock_profit_threshold or is_arbitrage

    def _check_arbitrage_opportunity(
            self,
            state: GabagoolState,
            up_price: float,
            down_price: float,
            portfolio: Portfolio,
    ) -> TradeDecision | None:
            """Check for arbitrage opportunity and return trade if found.
            
            Arbitrage: If we have one side and not the other, try to match shares.
            Execute if the resulting pair cost < min_arbitrage_pair_cost.
            """
            # Case 1: We have YES, try to match with NO
            if state.qty_yes > 0 and state.qty_no == 0:
                # Check if buying NO to match YES shares results in profitable pair cost
                trade = self._create_arbitrage_trade(
                    state, "NO", down_price, state.qty_yes, portfolio
                )
                if trade:
                    return trade
            
            # Case 2: We have NO, try to match with YES
            if state.qty_no > 0 and state.qty_yes == 0:
                # Check if buying YES to match NO shares results in profitable pair cost
                trade = self._create_arbitrage_trade(
                    state, "YES", up_price, state.qty_no, portfolio
                )
                if trade:
                    return trade
            
            return None

    def _create_arbitrage_trade(
            self,
            state: GabagoolState,
            side: str,
            price: float,
            target_qty: float,
            portfolio: Portfolio,
    ) -> TradeDecision | None:
            """Create an arbitrage trade to match shares exactly.
            
            For arbitrage, we need to match the exact number of shares on both sides.
            This ensures we lock in profit regardless of which side wins.
            
            Args:
                state: Current strategy state
                side: "YES" or "NO" to buy
                price: Price to buy at
                target_qty: Target quantity to match exactly (from the other side)
                portfolio: Portfolio for balance checks
            """
            # For arbitrage, we need to match shares exactly - ignore ratio limits
            # Calculate available capital
            available_capital = min(
                self.max_capital_per_market - (state.cost_yes + state.cost_no),
                portfolio.balance
            )
            
            # Calculate how many shares we can buy with available capital
            max_qty_by_capital = available_capital / price if price > 0 else 0
            
            # For arbitrage, try to match target_qty exactly
            # But we're limited by available capital
            actual_qty = min(target_qty, max_qty_by_capital)
            
            # Ensure we can buy at least some shares
            if actual_qty <= 0:
                return None
            
            # For true arbitrage, we should match exactly - if we can't afford it, don't do partial arbitrage
            # Only proceed if we can match at least 80% of target (allows for rounding)
            if actual_qty < target_qty * 0.8:
                return None
            
            # Simulate trade to check pair cost
            if side == "YES":
                new_cost_yes = state.cost_yes + (actual_qty * price)
                new_qty_yes = state.qty_yes + actual_qty
                new_avg_yes = self._avg(new_cost_yes, new_qty_yes)
                new_avg_no = self._avg(state.cost_no, state.qty_no)
            else:
                new_cost_no = state.cost_no + (actual_qty * price)
                new_qty_no = state.qty_no + actual_qty
                new_avg_yes = self._avg(state.cost_yes, state.qty_yes)
                new_avg_no = self._avg(new_cost_no, new_qty_no)
            
            new_pair_cost = new_avg_yes + new_avg_no
            
            # Only execute if pair cost <= min_arbitrage_pair_cost (profitable arbitrage)
            if new_pair_cost > self.min_arbitrage_pair_cost:
                return None
            
            trade_amount = actual_qty * price
            if trade_amount > portfolio.balance or trade_amount <= 0:
                return None
            
            # Lock profit after arbitrage
            state.locked_profit = True
            
            from polytrader.types import Outcome
            outcome: Outcome = "UP" if side == "YES" else "DOWN"
            
            return TradeDecision(
                market_id="",  # Will be set by caller
                outcome=outcome,
                amount=trade_amount,
                price=price,
            )

    def _is_hedged(self, state: GabagoolState) -> bool:
            """Check if we're hedged (profit > threshold).
            
            Always calculates worst case scenario: min_payout - total_cost.
            Only stop if profit > lock_profit_threshold (we've maximized profit enough).
            Continue trading even if loss <= threshold to maximize profit.
            """
            if state.qty_yes == 0 or state.qty_no == 0:
                return False
            
            min_payout = min(state.qty_yes, state.qty_no)  # Worst case payout
            total_cost = state.cost_yes + state.cost_no
            loss = total_cost - min_payout  # Worst case loss
            profit = min_payout - total_cost  # Worst case profit
            
            # Only consider hedged if profit exceeds lock_profit_threshold
            return profit > self.lock_profit_threshold

    def _should_buy_side(
            self,
            side: str,
            price: float,
            other_price: float,
            state: GabagoolState,
    ) -> bool:
            """Determine if we should buy a side based on price thresholds.
            
            Args:
                side: "YES" or "NO"
                price: Price of the side to potentially buy
                other_price: Price of the other side
                state: Current strategy state
                
            Returns:
                True if we should buy this side
            """
            has_side = (state.qty_yes > 0 if side == "YES" else state.qty_no > 0)
            has_other = (state.qty_no > 0 if side == "YES" else state.qty_yes > 0)
            
            # Validate price
            if price <= 0 or price >= self.max_buy_price:
                return False
            
            # No positions: buy whichever side hits accumulate_price or lower
            if not has_side and not has_other:
                # Buy if price <= accumulate_price (including prices below 0.6) and price < max_accumulate_price
                # But don't buy if price is too low (below hedge_price, that's a different signal)
                return (price <= self.accumulate_price and price < self.max_accumulate_price and price > self.hedge_price)
            
            # We have this side but not the other: prioritize getting the other side
            if has_side and not has_other:
                # Don't buy more of this side - we need to get the other side first
                # Exception: can average down if this side drops to hedge price and other is expensive
                if price <= self.hedge_price and other_price > self.hedge_price:
                    return True  # Average down this side
                return False  # Otherwise, wait for other side
            
            # We have the other side but not this side: prioritize hedging
            if has_other and not has_side:
                # Priority 1: Hedge if this side hits hedge price
                if price <= self.hedge_price:
                    return True
                # Priority 2: Accumulate if this side hits accumulate price or lower (but above hedge_price)
                return (price <= self.accumulate_price and price < self.max_accumulate_price and price > self.hedge_price)
            
            # We have both sides: continue accumulating both
            # Priority 1: Hedge if price is at hedge price
            if price <= self.hedge_price:
                return True
            # Priority 2: Accumulate if price is at accumulate price or lower (but above hedge_price)
            return (price <= self.accumulate_price and price < self.max_accumulate_price and price > self.hedge_price)

    def _get_max_qty_for_side(self, side: str, state: GabagoolState) -> float:
            """Get maximum quantity allowed for a side based on ratio limits."""
            if side == "YES":
                if state.qty_no > 0:
                    return state.qty_no * self.max_ratio
                else:
                    return self.max_order_size * self.max_ratio
            else:  # NO
                if state.qty_yes > 0:
                    return state.qty_yes * self.max_ratio
                else:
                    return self.max_order_size * self.max_ratio

    def _calculate_order_size(
            self,
            side: str,
            price: float,
            state: GabagoolState,
            available_capital: float,
    ) -> float:
            """Calculate order size for a side with all constraints.
            
            Returns:
                Order size in shares, or 0.0 if constraints can't be met
            """
            # Get max quantity based on ratio
            max_qty = self._get_max_qty_for_side(side, state)
            current_qty = state.qty_yes if side == "YES" else state.qty_no
            max_delta = max_qty - current_qty
            
            if max_delta <= 0:
                return 0.0
            
            # Calculate based on available capital
            capital_based_qty = available_capital / price
            delta_q = min(self.max_order_size, capital_based_qty, max_delta)
            
            # Ensure minimum trade size
            min_delta_q = self.min_trade_size / price
            if delta_q < min_delta_q:
                # Check if we can meet minimum within ratio limits
                if current_qty + min_delta_q <= max_qty:
                    delta_q = min_delta_q
                else:
                    return 0.0
            
            return delta_q

    def _simulate_trade(
            self,
            side: str,
            qty: float,
            price: float,
            state: GabagoolState,
    ) -> tuple[float, float, float, float]:
            """Simulate a trade and return new state.
            
            Returns:
                (new_qty_yes, new_cost_yes, new_qty_no, new_cost_no)
            """
            if side == "YES":
                return (
                    state.qty_yes + qty,
                    state.cost_yes + (qty * price),
                    state.qty_no,
                    state.cost_no,
                )
            else:
                return (
                    state.qty_yes,
                    state.cost_yes,
                    state.qty_no + qty,
                    state.cost_no + (qty * price),
                )

    def _validate_trade(
            self,
            side: str,
            qty: float,
            price: float,
            state: GabagoolState,
    ) -> bool:
            """Validate that a trade meets all constraints."""
            new_qty_yes, new_cost_yes, new_qty_no, new_cost_no = self._simulate_trade(
                side, qty, price, state
            )
            
            # Check ratio limits
            if side == "YES":
                max_qty = self._get_max_qty_for_side("YES", state)
                if new_qty_yes > max_qty:
                    return False
            else:
                max_qty = self._get_max_qty_for_side("NO", state)
                if new_qty_no > max_qty:
                    return False
            
            # Check profit threshold if we have both sides (worst case scenario)
            if new_qty_yes > 0 and new_qty_no > 0:
                min_payout = min(new_qty_yes, new_qty_no)  # Worst case payout
                total_cost = new_cost_yes + new_cost_no
                loss = total_cost - min_payout  # Worst case loss
                profit = min_payout - total_cost  # Worst case profit
                
                # Reject if profit exceeds lock_profit_threshold (we're done maximizing)
                if profit > self.lock_profit_threshold:
                    return False
                
                # Always allow trades that help maximize profit, regardless of loss
                # We continue trading to maximize profit even if loss is acceptable
            
            return True

    def decide(
            self,
            portfolio: Portfolio,
            market_id: str,
            up_price: float,
            down_price: float,
            timestamp: float | None = None,
    ) -> TradeDecision | None:
            """Make gabagool-style trading decision."""
            now = timestamp if timestamp is not None else time.time()
            state = self._get_state(market_id)
            self._update_state_from_portfolio(portfolio, market_id, state)

            # Early exit checks
            if state.locked_profit:
                return None
            
            if portfolio.balance < self.min_trade_size:
                return None
            
            total_invested = state.cost_yes + state.cost_no
            if total_invested >= self.max_capital_per_market:
                return None
            
            available_capital = min(
                self.max_capital_per_market - total_invested,
                portfolio.balance
            )

            # Check if we already have arbitrage (matching shares with profitable pair cost)
            if state.qty_yes > 0 and state.qty_no > 0:
                avg_yes = self._avg(state.cost_yes, state.qty_yes)
                avg_no = self._avg(state.cost_no, state.qty_no)
                pair_cost = avg_yes + avg_no
                # Check if shares match (within 5% difference)
                shares_match = abs(state.qty_yes - state.qty_no) / max(state.qty_yes, state.qty_no) < 0.05 if max(state.qty_yes, state.qty_no) > 0 else False
                
                # If shares match and pair cost is profitable (<= min_arbitrage_pair_cost), lock arbitrage
                if shares_match and pair_cost <= self.min_arbitrage_pair_cost:
                    # We already have arbitrage - lock profit and stop trading
                    state.locked_profit = True
                    return None

            # Check for arbitrage opportunity (when we have one side and not the other)
            arbitrage_trade = self._check_arbitrage_opportunity(
                state, up_price, down_price, portfolio
            )
            if arbitrage_trade:
                arbitrage_trade.market_id = market_id
                # Per-side rate limiting: check the specific outcome we want to trade
                outcome = arbitrage_trade.outcome
                last_trade_time_for_side = state.get_last_trade_time(outcome)
                if now - last_trade_time_for_side < self.min_seconds_between_trades:
                    return None
                # Don't update last_trade_time here - wait for successful execution
                # The manager will call on_trade_executed() after successful trade
                return arbitrage_trade

            # Check if already hedged
            if self._is_hedged(state):
                state.locked_profit = True
                return None

            # Determine which side to buy
            side_to_buy: str | None = None
            price_to_buy: float = 0.0

            # If loss > threshold, prioritize buying the side that helps balance
            if state.qty_yes > 0 and state.qty_no > 0:
                min_payout = min(state.qty_yes, state.qty_no)
                total_cost = state.cost_yes + state.cost_no
                current_loss = total_cost - min_payout
                
                # If loss > threshold, prioritize buying the side with fewer shares to balance
                if current_loss > self.max_loss_threshold:
                    if state.qty_yes < state.qty_no:
                        # YES has fewer shares, prioritize buying YES to balance
                        if (up_price <= self.hedge_price or 
                            (self.accumulate_price <= up_price < self.max_accumulate_price)):
                            max_yes_qty = self._get_max_qty_for_side("YES", state)
                            if state.qty_yes < max_yes_qty:
                                side_to_buy = "YES"
                                price_to_buy = up_price
                    elif state.qty_no < state.qty_yes:
                        # NO has fewer shares, prioritize buying NO to balance
                        if (down_price <= self.hedge_price or 
                            (self.accumulate_price <= down_price < self.max_accumulate_price)):
                            max_no_qty = self._get_max_qty_for_side("NO", state)
                            if state.qty_no < max_no_qty:
                                side_to_buy = "NO"
                                price_to_buy = down_price

            # If no balancing trade needed, check for normal hedging/accumulation opportunities
            if side_to_buy is None:
                # Priority 1: Check for hedging opportunities (price <= hedge_price)
                # BUT: If we have one side and the other hits hedge_price, ALWAYS match shares for arbitrage
                if state.qty_yes > 0 and state.qty_no == 0:
                    # We have YES, if NO hits hedge_price, match shares for arbitrage
                    if down_price <= self.hedge_price:
                        # Match shares exactly - this is hedging, so we match regardless of pair cost
                        target_qty = state.qty_yes
                        available_capital = min(
                            self.max_capital_per_market - (state.cost_yes + state.cost_no),
                            portfolio.balance
                        )
                        max_qty_by_capital = available_capital / down_price if down_price > 0 else 0
                        actual_qty = min(target_qty, max_qty_by_capital)
                        
                        if actual_qty > 0 and actual_qty >= target_qty * 0.8:  # Allow 80% match minimum
                            trade_amount = actual_qty * down_price
                            if trade_amount <= portfolio.balance and trade_amount > 0:
                                # Per-side rate limiting: check DOWN side
                                last_trade_time_down = state.get_last_trade_time("DOWN")
                                if now - last_trade_time_down < self.min_seconds_between_trades:
                                    return None
                                # Avoid trading at the exact same price for the same outcome
                                if last_trade_time_down > 0:
                                    price_tolerance = 0.001
                                    if (abs(down_price - state.last_trade_price) < price_tolerance and
                                        now - last_trade_time_down < self.min_seconds_between_trades * 2):
                                        return None
                                # Don't update last_trade_time here - wait for successful execution
                                # The manager will call on_trade_executed() after successful trade
                                from polytrader.types import Outcome
                                return TradeDecision(
                                    market_id=market_id,
                                    outcome="DOWN",
                                    amount=trade_amount,
                                    price=down_price,
                                )
                
                if state.qty_no > 0 and state.qty_yes == 0:
                    # We have NO, if YES hits hedge_price, match shares for arbitrage
                    if up_price <= self.hedge_price:
                        # Match shares exactly - this is hedging, so we match regardless of pair cost
                        target_qty = state.qty_no
                        available_capital = min(
                            self.max_capital_per_market - (state.cost_yes + state.cost_no),
                            portfolio.balance
                        )
                        max_qty_by_capital = available_capital / up_price if up_price > 0 else 0
                        actual_qty = min(target_qty, max_qty_by_capital)
                        
                        if actual_qty > 0 and actual_qty >= target_qty * 0.8:  # Allow 80% match minimum
                            trade_amount = actual_qty * up_price
                            if trade_amount <= portfolio.balance and trade_amount > 0:
                                # Per-side rate limiting: check UP side
                                last_trade_time_up = state.get_last_trade_time("UP")
                                if now - last_trade_time_up < self.min_seconds_between_trades:
                                    return None
                                # Avoid trading at the exact same price for the same outcome
                                if last_trade_time_up > 0:
                                    price_tolerance = 0.001
                                    if (abs(up_price - state.last_trade_price) < price_tolerance and
                                        now - last_trade_time_up < self.min_seconds_between_trades * 2):
                                        return None
                                # Don't update last_trade_time here - wait for successful execution
                                # The manager will call on_trade_executed() after successful trade
                                from polytrader.types import Outcome
                                return TradeDecision(
                                    market_id=market_id,
                                    outcome="UP",
                                    amount=trade_amount,
                                    price=up_price,
                                )
                
                # Normal hedging logic (when we already have both sides or arbitrage didn't work)
                if down_price <= self.hedge_price and self._should_buy_side("NO", down_price, up_price, state):
                    max_no_qty = self._get_max_qty_for_side("NO", state)
                    if state.qty_no < max_no_qty:
                        side_to_buy = "NO"
                        price_to_buy = down_price
                
                if up_price <= self.hedge_price and self._should_buy_side("YES", up_price, down_price, state):
                    max_yes_qty = self._get_max_qty_for_side("YES", state)
                    if state.qty_yes < max_yes_qty:
                        # Only override if we don't have a hedge trade or YES hedge is better
                        if side_to_buy is None:
                            side_to_buy = "YES"
                            price_to_buy = up_price
                
                # Priority 2: Check for accumulation opportunities (accumulate_price <= price < max_accumulate_price)
                if side_to_buy is None:
                    if self._should_buy_side("YES", up_price, down_price, state):
                        max_yes_qty = self._get_max_qty_for_side("YES", state)
                        if state.qty_yes < max_yes_qty:
                            side_to_buy = "YES"
                            price_to_buy = up_price
                    
                    if self._should_buy_side("NO", down_price, up_price, state):
                        max_no_qty = self._get_max_qty_for_side("NO", state)
                        if state.qty_no < max_no_qty:
                            # Only override if we don't have YES or NO is better
                            if side_to_buy is None:
                                side_to_buy = "NO"
                                price_to_buy = down_price

            if side_to_buy is None:
                return None

            # Per-side rate limiting: check the specific side we want to trade
            outcome_for_rate_limit = "UP" if side_to_buy == "YES" else "DOWN"
            last_trade_time_for_side = state.get_last_trade_time(outcome_for_rate_limit)
            if now - last_trade_time_for_side < self.min_seconds_between_trades:
                return None
            
            # Avoid trading at the exact same price for the same outcome
            if last_trade_time_for_side > 0:
                price_tolerance = 0.001  # 0.1% tolerance
                if outcome_for_rate_limit == "UP" and state.qty_yes > 0:
                    if (abs(up_price - state.last_trade_price) < price_tolerance and
                        now - last_trade_time_for_side < self.min_seconds_between_trades * 2):
                        return None
                elif outcome_for_rate_limit == "DOWN" and state.qty_no > 0:
                    if (abs(down_price - state.last_trade_price) < price_tolerance and
                        now - last_trade_time_for_side < self.min_seconds_between_trades * 2):
                        return None

            # Validate price
            if price_to_buy <= 0 or price_to_buy >= self.max_buy_price:
                return None

            # Calculate order size
            delta_q = self._calculate_order_size(
                side_to_buy, price_to_buy, state, available_capital
            )
            
            if delta_q <= 0:
                return None

            # Validate trade
            if not self._validate_trade(side_to_buy, delta_q, price_to_buy, state):
                return None

            trade_amount = delta_q * price_to_buy
            if trade_amount > portfolio.balance:
                return None

            # Don't update last_trade_time here - wait for successful execution
            # The manager will call on_trade_executed() after successful trade

            # Create trade decision
            from polytrader.types import Outcome
            outcome: Outcome = "UP" if side_to_buy == "YES" else "DOWN"

            return TradeDecision(
                market_id=market_id,
                outcome=outcome,
                amount=trade_amount,
                price=price_to_buy,
            )
    
    def get_metrics(self, portfolio: Portfolio, market_id: str) -> dict[str, float | int | bool]:
            """Get strategy metrics for a market."""
            state = self._get_state(market_id)
            self._update_state_from_portfolio(portfolio, market_id, state)

            pair_cost = self._pair_cost(
                state.cost_yes, state.qty_yes, state.cost_no, state.qty_no
            )
            min_payout = min(state.qty_yes, state.qty_no) if state.qty_yes > 0 and state.qty_no > 0 else 0.0
            total_cost = state.cost_yes + state.cost_no
            estimated_profit = min_payout - total_cost if min_payout > 0 else 0.0

            return {
                "pair_cost": pair_cost,
                "qty_yes": state.qty_yes,
                "qty_no": state.qty_no,
                "cost_yes": state.cost_yes,
                "cost_no": state.cost_no,
                "locked_profit": state.locked_profit,
                "estimated_profit": estimated_profit,
                "trade_count": state.trade_count,
            }
