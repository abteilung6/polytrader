"""Utility functions for the UI."""

from collections import defaultdict
from datetime import datetime

from polytrader.core.manager import PortfolioManager
from polytrader.core.strategies import create_strategy
from polytrader.types import MarketTick, Outcome

from backtest import get_market_expiration_time, load_ticks_from_csv
from ui.models import MarketProfitResult, PricePoint, TradeEvent


def simulate_backtest_with_tracking(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
    timestamp_cutoff: float | None = None,
) -> tuple[list[PricePoint], list[TradeEvent]]:
    """Run backtest and track all price movements and trades.

    Returns:
        Tuple of (price_points, trade_events)
    """
    # Load all ticks
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)

    if timestamp_cutoff is not None:
        all_ticks = [tick for tick in all_ticks if tick.ts >= timestamp_cutoff]

    if not all_ticks:
        return [], []

    all_ticks.sort(key=lambda t: t.ts)

    # Initialize portfolio manager
    strategy = create_strategy(strategy_name)
    portfolio_manager = PortfolioManager(
        initial_balance=initial_balance,
        strategy=strategy,
    )

    # Group ticks by timestamp
    tick_groups: dict[float, dict[Outcome, MarketTick]] = defaultdict(dict)
    for tick in all_ticks:
        rounded_ts = round(tick.ts, 1)
        tick_groups[rounded_ts][tick.outcome] = tick

    price_points: list[PricePoint] = []
    trade_events: list[TradeEvent] = []

    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None

    for ts in processed_timestamps:
        group = tick_groups[ts]

        # Update latest ticks
        if "UP" in group:
            latest_up_tick = group["UP"]
        if "DOWN" in group:
            latest_down_tick = group["DOWN"]

        # Get current prices
        if latest_up_tick and latest_down_tick:
            # Check if timestamps match (within tolerance)
            timestamp_diff = abs(latest_up_tick.ts - latest_down_tick.ts)
            if timestamp_diff <= 0.1:
                up_price = latest_up_tick.best_ask
                down_price = latest_down_tick.best_ask

                # Get current positions
                up_pos = portfolio_manager.portfolio.get_position(market_id, "UP")
                down_pos = portfolio_manager.portfolio.get_position(market_id, "DOWN")

                up_shares = up_pos.quantity if up_pos else 0.0
                down_shares = down_pos.quantity if down_pos else 0.0
                balance = portfolio_manager.get_balance()

                # Record price point
                price_points.append(
                    PricePoint(
                        timestamp=ts,
                        up_price=up_price,
                        down_price=down_price,
                        balance=balance,
                        up_shares=up_shares,
                        down_shares=down_shares,
                    )
                )

                # Process trading decision
                decision = portfolio_manager.process_prices(
                    market_id=market_id,
                    up_price=up_price,
                    down_price=down_price,
                    timestamp=ts,
                )

                # Record trade if executed
                if decision:
                    trades = decision if isinstance(decision, list) else [decision]
                    balance_after = portfolio_manager.get_balance()

                    for trade in trades:
                        shares = trade.amount / trade.price if trade.price > 0 else 0
                        trade_events.append(
                            TradeEvent(
                                timestamp=ts,
                                outcome=trade.outcome,
                                amount=trade.amount,
                                price=trade.price,
                                shares=shares,
                                balance=balance_after,
                                up_price=up_price,
                                down_price=down_price,
                            )
                        )

    return price_points, trade_events


def calculate_market_profit(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
) -> MarketProfitResult:
    """Calculate profit for a single market.
    
    This matches the backtest script logic by settling positions at market expiration.
    """
    # Load all ticks
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)
    
    if not all_ticks:
        return MarketProfitResult(
            market_id=market_id,
            profit=0.0,
            profit_pct=0.0,
            final_balance=initial_balance,
            total_trades=0,
            total_spent=0.0,
            final_up_shares=0.0,
            final_down_shares=0.0,
            profit_if_up_wins=0.0,
            profit_if_down_wins=0.0,
        )
    
    all_ticks.sort(key=lambda t: t.ts)
    
    # Initialize portfolio manager (single run for consistency with backtest script)
    strategy = create_strategy(strategy_name)
    portfolio_manager = PortfolioManager(
        initial_balance=initial_balance,
        strategy=strategy,
    )
    
    # Group ticks by timestamp and process trades
    tick_groups: dict[float, dict[Outcome, MarketTick]] = defaultdict(dict)
    for tick in all_ticks:
        rounded_ts = round(tick.ts, 1)
        tick_groups[rounded_ts][tick.outcome] = tick
    
    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None
    
    for ts in processed_timestamps:
        group = tick_groups[ts]
        
        # Update latest ticks
        if "UP" in group:
            latest_up_tick = group["UP"]
        if "DOWN" in group:
            latest_down_tick = group["DOWN"]
        
        # Process trades when we have both UP and DOWN ticks
        if latest_up_tick and latest_down_tick:
            timestamp_diff = abs(latest_up_tick.ts - latest_down_tick.ts)
            if timestamp_diff <= 0.1:
                portfolio_manager.process_prices(
                    market_id=market_id,
                    up_price=latest_up_tick.best_ask,
                    down_price=latest_down_tick.best_ask,
                    timestamp=ts,
                )
    
    # Get positions before settlement (matches backtest script logic)
    up_position_before = portfolio_manager.portfolio.get_position(market_id, "UP")
    down_position_before = portfolio_manager.portfolio.get_position(market_id, "DOWN")
    
    total_cost_before_settlement = (
        (up_position_before.quantity * up_position_before.avg_price if up_position_before else 0)
        + (down_position_before.quantity * down_position_before.avg_price if down_position_before else 0)
    )
    
    final_up_shares = up_position_before.quantity if up_position_before else 0.0
    final_down_shares = down_position_before.quantity if down_position_before else 0.0
    
    # Get statistics before settlement
    stats_before_settlement = portfolio_manager.get_statistics()
    balance_before_settlement = stats_before_settlement["balance"]
    total_trades = stats_before_settlement["total_trades"]
    total_spent = stats_before_settlement["total_spent"]
    
    # Calculate profit scenarios (hypothetical, before settlement)
    profit_if_up_wins = (final_up_shares * 1.0) - total_cost_before_settlement
    profit_if_down_wins = (final_down_shares * 1.0) - total_cost_before_settlement
    
    # Settle positions at market expiration (like backtest script)
    expiration_time = get_market_expiration_time(market_id)
    winner: str | None = None
    actual_profit = 0.0
    final_balance = balance_before_settlement
    
    if expiration_time and latest_up_tick and latest_down_tick:
        # Use final prices to determine winner
        final_up_price = latest_up_tick.best_ask
        final_down_price = latest_down_tick.best_ask
        
        # Settle positions (adds payout to balance)
        settlement = portfolio_manager.expire_positions(
            market_id=market_id,
            up_price=final_up_price,
            down_price=final_down_price,
        )
        winner = settlement["winner"]
        
        # Calculate actual profit after settlement (matches backtest script logic exactly)
        if up_position_before and down_position_before:
            # Hedged position
            if winner == "UP":
                actual_payout = final_up_shares * 1.0
            else:  # DOWN wins
                actual_payout = final_down_shares * 1.0
            actual_profit = actual_payout - total_cost_before_settlement
        elif up_position_before:
            # Only UP position
            actual_payout = final_up_shares * 1.0 if winner == "UP" else 0.0
            actual_profit = actual_payout - total_cost_before_settlement
        elif down_position_before:
            # Only DOWN position
            actual_payout = final_down_shares * 1.0 if winner == "DOWN" else 0.0
            actual_profit = actual_payout - total_cost_before_settlement
        else:
            # No positions
            actual_profit = 0.0
        
        # Get final balance after settlement
        stats_after_settlement = portfolio_manager.get_statistics()
        final_balance = stats_after_settlement["balance"]
    else:
        # Market hasn't expired, use hypothetical scenarios (average)
        actual_profit = (profit_if_up_wins + profit_if_down_wins) / 2.0
        final_balance = balance_before_settlement
    
    # Calculate profit percentage (matches backtest script)
    profit = final_balance - initial_balance  # Should equal actual_profit after settlement
    profit_pct = (profit / initial_balance * 100) if initial_balance > 0 else 0.0

    return MarketProfitResult(
        market_id=market_id,
        profit=actual_profit,  # Use actual profit from settlement (matches backtest script)
        profit_pct=profit_pct,
        final_balance=final_balance,
        total_trades=total_trades,
        total_spent=total_spent,
        final_up_shares=final_up_shares,
        final_down_shares=final_down_shares,
        profit_if_up_wins=profit_if_up_wins,
        profit_if_down_wins=profit_if_down_wins,
    )

