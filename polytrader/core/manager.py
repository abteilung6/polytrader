"""Portfolio manager for executing trades."""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.clob import place_market_order
from polytrader.core.portfolio import Portfolio
from polytrader.core.strategy import Strategy
from polytrader.core.trade import TradeDecision
from polytrader.types import CandleData, MarketTick, Outcome

if TYPE_CHECKING:
    from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
    from polytrader.gamma import GammaClient


class PortfolioManager:
    """Manages portfolio and executes trades based on strategy."""

    def __init__(
        self,
        initial_balance: float = 1000.0,
        strategy: Strategy | None = None,
        execute_real_orders: bool = False,
        clob_client: "ClobClient | None" = None,
        gamma_client: "GammaClient | None" = None,
    ) -> None:
        """Initialize portfolio manager.

        Args:
            initial_balance: Starting USDC balance
            strategy: Trading strategy to use (required)
            execute_real_orders: If True, execute real orders on Polymarket
            clob_client: ClobClient instance for real order execution (required if execute_real_orders=True)
            gamma_client: GammaClient instance for getting token IDs (required if execute_real_orders=True)
        """
        self.portfolio = Portfolio(balance=initial_balance)
        self.strategy = strategy
        self.total_trades = 0
        self.total_spent = 0.0
        self.execute_real_orders = execute_real_orders
        self.clob_client = clob_client
        self.gamma_client = gamma_client
        self._portfolio_lock = threading.Lock()  # Lock for thread-safe portfolio updates
        
        if execute_real_orders:
            if clob_client is None:
                raise ValueError("clob_client is required when execute_real_orders=True")
            if gamma_client is None:
                raise ValueError("gamma_client is required when execute_real_orders=True")

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
        timestamp: float | None = None,
    ) -> TradeDecision | list[TradeDecision] | None:
        """Process prices for both outcomes and potentially execute a trade.

        This is useful when you have prices for both UP and DOWN outcomes.

        Args:
            market_id: Market identifier
            up_price: Current mid price for UP outcome
            down_price: Current mid price for DOWN outcome
            timestamp: Optional timestamp for backtesting (defaults to None)

        Returns:
            TradeDecision or list of TradeDecisions if trades were made, None otherwise
        """
        # Get decision from strategy
        decision = self.strategy.decide(
            portfolio=self.portfolio,
            market_id=market_id,
            up_price=up_price,
            down_price=down_price,
            timestamp=timestamp,
        )

        if decision is None:
            return None

        # Handle both single decision and list of decisions (for arbitrage)
        if isinstance(decision, list):
            # Execute all trades in parallel
            with ThreadPoolExecutor(max_workers=len(decision)) as executor:
                futures = {
                    executor.submit(self._execute_trade, trade, timestamp): trade
                    for trade in decision
                }
                # Wait for all trades to complete
                for future in as_completed(futures):
                    try:
                        future.result()  # This will raise any exceptions that occurred
                    except Exception as e:
                        trade = futures[future]
                        print(f"   ⚠️  Error executing trade for {trade.outcome}: {e}")
            return decision
        else:
            # Execute single trade
            self._execute_trade(decision, timestamp=timestamp)
            return decision

    def _execute_trade(self, decision: TradeDecision, timestamp: float | None = None) -> None:
        """Execute a trade (simulated or real).

        Args:
            decision: Trade decision to execute
            timestamp: Optional timestamp for backtesting (defaults to None)
        """
        # Validate price to prevent division by zero
        if decision.price <= 0:
            raise ValueError(f"Invalid trade price: {decision.price}. Price must be > 0.")
        
        # Execute real order on Polymarket if enabled
        order_successful = False
        taking_amount_str = ""
        making_amount_str = ""
        if self.execute_real_orders and self.clob_client and self.gamma_client:
            # Try to place order, with one retry if it fails
            for attempt in range(2):  # Try twice
                try:
                    # Get token ID for this market/outcome
                    market = self.gamma_client.get_market_by_slug(decision.market_id)
                    # Convert internal format ("UP"/"DOWN") to API format ("Up"/"Down")
                    outcome_api = "Up" if decision.outcome == "UP" else "Down"
                    token_id = market.get_token_id(outcome_api)
                    
                    # Place real order on Polymarket
                    if attempt == 0:
                        print(f"\n💸 Executing REAL order:")
                    else:
                        print(f"\n🔄 Retrying REAL order (attempt {attempt + 1}):")
                    print(f"   Market: {decision.market_id}")
                    print(f"   Outcome: {decision.outcome}")
                    print(f"   Amount: ${decision.amount:.2f} USDC")
                    print(f"   Price: ${decision.price:.4f}")
                    print(f"   Token ID: {token_id}")
                    
                    response = place_market_order(
                        client=self.clob_client,
                        token_id=token_id,
                        amount=decision.amount,
                        side=BUY,
                    )
                    
                    # Check if order was successful
                    success = response.get("success", False)
                    error_msg = response.get("errorMsg", "")
                    order_id = response.get("orderID", "")
                    status = response.get("status", "")
                    taking_amount_str = response.get("takingAmount", "")
                    making_amount_str = response.get("makingAmount", "")
                    
                    if success:
                        order_successful = True
                        print(f"   ✅ Order executed successfully!")
                        print(f"   Order ID: {order_id}")
                        print(f"   Status: {status}")
                        if taking_amount_str:
                            print(f"   Shares received: {taking_amount_str}")
                        if making_amount_str:
                            print(f"   USDC spent: {making_amount_str}")
                        break  # Success, exit retry loop
                    else:
                        print(f"   ❌ Order failed!")
                        if error_msg:
                            print(f"   Error: {error_msg}")
                        if order_id:
                            print(f"   Order ID: {order_id}")
                        if status:
                            print(f"   Status: {status}")
                        # Continue to retry if this was first attempt
                        if attempt == 0:
                            print(f"   Will retry once...")
                        else:
                            print(f"   Max retries reached. Skipping this trade.")
                
                except Exception as e:
                    print(f"   ❌ Error executing real order: {e}")
                    if attempt == 0:
                        print(f"   Will retry once...")
                    else:
                        print(f"   Max retries reached. Skipping this trade.")
            
            # If real order failed after retries, don't update portfolio
            if not order_successful:
                print(f"   ⚠️  Order not successful. Portfolio not updated. Waiting for next opportunity.")
                # Notify strategy that trade failed
                if hasattr(self.strategy, 'on_trade_failed'):
                    self.strategy.on_trade_failed(
                        market_id=decision.market_id,
                        outcome=decision.outcome,
                        price=decision.price,
                        timestamp=timestamp,
                    )
                return
            
            # Extract actual values from successful order response
            if order_successful:
                # Get actual shares received and USDC spent from response
                actual_quantity = float(taking_amount_str) if taking_amount_str else None
                actual_amount_spent = float(making_amount_str) if making_amount_str else None
                
                if actual_quantity is None or actual_amount_spent is None:
                    print(f"   ⚠️  Warning: Could not parse response values. Using estimated values.")
                    actual_quantity = decision.amount / decision.price
                    actual_amount_spent = decision.amount
                    actual_price = decision.price
                else:
                    # Calculate actual price per share based on what we actually paid
                    actual_price = actual_amount_spent / actual_quantity if actual_quantity > 0 else decision.price
                
                # Update portfolio with actual values from order (thread-safe)
                with self._portfolio_lock:
                    self.portfolio.balance -= actual_amount_spent
                    self.portfolio.add_position(
                        market_id=decision.market_id,
                        outcome=decision.outcome,
                        quantity=actual_quantity,
                        price=actual_price,
                    )
                    
                    # Track statistics
                    self.total_trades += 1
                    self.total_spent += actual_amount_spent
                
                # Notify strategy that trade was executed successfully
                if hasattr(self.strategy, 'on_trade_executed'):
                    self.strategy.on_trade_executed(
                        market_id=decision.market_id,
                        outcome=decision.outcome,
                        price=actual_price,
                        timestamp=timestamp,  # Use provided timestamp (None for real trades)
                    )
                return
        
        # Simulated trading: calculate quantity based on amount and price
        # Validate price to prevent division by zero or infinity
        if decision.price <= 0 or not (0 < decision.price <= 1.0):
            print(f"   ⚠️  Warning: Invalid price {decision.price} for trade. Skipping.")
            return
        
        quantity = decision.amount / decision.price
        
        # Validate quantity is finite
        if not (0 <= quantity < float('inf')):
            print(f"   ⚠️  Warning: Invalid quantity {quantity} for trade (price={decision.price}, amount={decision.amount}). Skipping.")
            return

        # Update portfolio (simulated trading, thread-safe)
        with self._portfolio_lock:
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
        
        # Notify strategy that trade was executed successfully
        if hasattr(self.strategy, 'on_trade_executed'):
            self.strategy.on_trade_executed(
                market_id=decision.market_id,
                outcome=decision.outcome,
                price=decision.price,
                timestamp=timestamp,  # Use provided timestamp (None for simulated trades)
            )

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
                
                # Validate position quantity is finite before calculating payout
                if not (0 <= position.quantity < float('inf')):
                    print(f"   ⚠️  Warning: Invalid position quantity {position.quantity} for {outcome}. Skipping payout.")
                    positions_settled += 1
                    continue
                
                # If this position's outcome matches the winner, pay out $1.00 per share
                if outcome == winner:
                    payout = position.quantity * 1.0
                    # Validate payout is finite
                    if 0 <= payout < float('inf'):
                        self.portfolio.balance += payout
                        total_payout += payout
                    else:
                        print(f"   ⚠️  Warning: Invalid payout {payout} for {outcome} position. Skipping.")
                
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

