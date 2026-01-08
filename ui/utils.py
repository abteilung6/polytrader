"""Utility functions for the UI."""

from collections import defaultdict
from datetime import datetime

from polytrader.core.manager import PortfolioManager
from polytrader.core.strategies import create_strategy
from polytrader.types import MarketTick, Outcome

from backtest import load_ticks_from_csv
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
    """Calculate profit for a single market."""
    price_points, trade_events = simulate_backtest_with_tracking(
        market_id=market_id,
        csv_files=csv_files,
        strategy_name=strategy_name,
        initial_balance=initial_balance,
    )

    if not price_points:
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

    final_balance = price_points[-1].balance
    final_up_shares = price_points[-1].up_shares
    final_down_shares = price_points[-1].down_shares

    total_trades = len(trade_events)
    total_spent = sum(te.amount for te in trade_events)

    # Calculate profit scenarios
    profit_if_up_wins = (final_balance + final_up_shares * 1.0) - initial_balance
    profit_if_down_wins = (final_balance + final_down_shares * 1.0) - initial_balance

    # Use average of both scenarios as estimated profit
    estimated_profit = (profit_if_up_wins + profit_if_down_wins) / 2.0
    profit_pct = (estimated_profit / initial_balance * 100) if initial_balance > 0 else 0.0

    return MarketProfitResult(
        market_id=market_id,
        profit=estimated_profit,
        profit_pct=profit_pct,
        final_balance=final_balance,
        total_trades=total_trades,
        total_spent=total_spent,
        final_up_shares=final_up_shares,
        final_down_shares=final_down_shares,
        profit_if_up_wins=profit_if_up_wins,
        profit_if_down_wins=profit_if_down_wins,
    )

