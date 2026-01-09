"""Display formatting functions for CLI output."""

from datetime import datetime
from typing import TYPE_CHECKING

from polytrader.core.portfolio import Portfolio
from polytrader.types import MarketTick, Outcome

if TYPE_CHECKING:
    from polytrader.core.manager import PortfolioManager
    from polytrader.core.position import Position


def print_watch_header(outcomes_to_watch: list[str]) -> str:
    """Print table header for watch mode and return header string."""
    if len(outcomes_to_watch) > 1:
        # Table format for multiple outcomes
        header = f"{'Outcome':<10} {'Best Bid':<12} {'Best Ask':<12} {'Mid Price':<12} {'Spread':<12} {'Timestamp':<12}"
        print(header)
        print("-" * len(header))
    else:
        # Single outcome format
        header = f"{'Tick':<6} {'Best Bid':<12} {'Best Ask':<12} {'Mid Price':<12} {'Spread':<12} {'Timestamp':<12}"
        print(header)
        print("-" * 70)
    return header


def print_tick_table(
    count: int,
    outcomes_to_watch: list[str],
    latest_ticks: dict[str, MarketTick],
    header: str,
) -> None:
    """Print tick data in table format."""
    if len(outcomes_to_watch) > 1:
        # Display table with all outcomes side by side
        if count == 1:
            print()  # Extra line before first table
        print(f"\n--- Update #{count} ---")
        print(header)
        print("-" * len(header))
        
        # Show all outcomes
        for outcome_cli in outcomes_to_watch:
            outcome_type = "UP" if outcome_cli == "Up" else "DOWN"
            if outcome_type in latest_ticks:
                t = latest_ticks[outcome_type]
                print(
                    f"{outcome_cli:<10} {t.best_bid:<12.4f} {t.best_ask:<12.4f} "
                    f"{t.mid:<12.4f} {t.spread:<12.4f} {t.ts:<12.3f}"
                )
            else:
                print(f"{outcome_cli:<10} {'-':<12} {'-':<12} {'-':<12} {'-':<12} {'-':<12}")
    else:
        # Single outcome - simple row format
        tick = list(latest_ticks.values())[0] if latest_ticks else None
        if tick:
            print(
                f"{count:<6} {tick.best_bid:<12.4f} {tick.best_ask:<12.4f} "
                f"{tick.mid:<12.4f} {tick.spread:<12.4f} {tick.ts:<12.3f}"
            )


def print_portfolio_info(
    portfolio_manager: "PortfolioManager",
    tick: MarketTick,
    latest_ticks: dict[str, MarketTick],
    market_prices: dict[tuple[str, Outcome], float],
    initial_balance: float,
) -> None:
    """Print portfolio information for current market."""
    stats = portfolio_manager.get_statistics()
    portfolio = portfolio_manager.get_portfolio()
    
    # Build price dictionary for all positions
    current_prices: dict[tuple[str, Outcome], float] = {}
    for (market_id, outcome), position in portfolio.positions.items():
        price_key = (market_id, outcome)
        if price_key in market_prices:
            current_prices[price_key] = market_prices[price_key]
        else:
            current_prices[price_key] = position.avg_price
    
    # Calculate total portfolio value
    total_portfolio_value = portfolio.get_total_value(current_prices)
    total_profit = total_portfolio_value - initial_balance
    
    # Get current market prices for display
    up_tick = latest_ticks.get("UP")
    down_tick = latest_ticks.get("DOWN")
    
    # Calculate profit scenarios for this market
    market_positions = {
        outcome: pos
        for (m_id, outcome), pos in portfolio.positions.items()
        if m_id == tick.market_id
    }
    
    if market_positions:
        # Calculate total cost for all positions in this market
        total_cost = sum(
            pos.quantity * pos.avg_price
            for pos in market_positions.values()
        )
        
        # Calculate profit if UP wins
        up_position = market_positions.get("UP")
        down_position = market_positions.get("DOWN")
        up_value_if_up_wins = (up_position.quantity * 1.0) if up_position else 0.0
        down_value_if_up_wins = (down_position.quantity * 0.0) if down_position else 0.0
        profit_if_up = (up_value_if_up_wins + down_value_if_up_wins) - total_cost
        
        # Calculate profit if DOWN wins
        up_value_if_down_wins = (up_position.quantity * 0.0) if up_position else 0.0
        down_value_if_down_wins = (down_position.quantity * 1.0) if down_position else 0.0
        profit_if_down = (up_value_if_down_wins + down_value_if_down_wins) - total_cost
        
        print(f"\n💼 Portfolio: Cash=${stats['balance']:.2f} | Total Value=${total_portfolio_value:.2f} | Profit=${total_profit:+.2f} | Trades={stats['total_trades']} | Positions={stats['num_positions']}")
        print(f"   Profit if UP: ${profit_if_up:+.2f}")
        print(f"   Profit if DOWN: ${profit_if_down:+.2f}")
        
        # Show positions for current market
        if up_tick and down_tick:
            print(f"\n   Positions in {tick.market_id}:")
            for outcome, position in market_positions.items():
                current_price = current_prices.get((tick.market_id, outcome), position.avg_price)
                print(
                    f"     {outcome}: {position.quantity:.4f} @ ${position.avg_price:.4f} "
                    f"(Current: ${current_price:.4f})"
                )


def print_trade_executed(decision: object, market_id: str) -> None:
    """Print trade execution message."""
    if isinstance(decision, list):
        # Multiple trades executed (e.g., arbitrage strategy buying both sides)
        outcomes = ", ".join(d.outcome for d in decision)
        total_cost = sum(d.amount for d in decision)
        print(f"✅ Trades executed on {market_id}: {outcomes} (total: ${total_cost:.2f})")
    else:
        print(f"✅ Trade executed on {market_id}: {decision.outcome}")


def print_market_expired(
    market_id: str,
    winner: str,
    up_price: float,
    down_price: float,
    positions_settled: int,
    total_payout: float,
    balance: float,
) -> None:
    """Print market expiration message."""
    print(f"\n⏰ Market expired: {market_id}")
    print(f"   Winner: {winner} (UP: ${up_price:.4f}, DOWN: ${down_price:.4f})")
    print(f"   Positions settled: {positions_settled}")
    print(f"   Total payout: ${total_payout:.2f} USDC")
    print(f"   New balance: ${balance:.2f} USDC")
    print()


def print_final_portfolio_stats(
    portfolio_manager: "PortfolioManager",
    market_prices: dict[tuple[str, Outcome], float],
    initial_balance: float,
) -> None:
    """Print final portfolio statistics."""
    stats = portfolio_manager.get_statistics()
    portfolio = portfolio_manager.get_portfolio()
    
    # Build final prices using market_prices (current prices) or entry prices as fallback
    final_prices: dict[tuple[str, Outcome], float] = {}
    for (market_id, outcome), position in portfolio.positions.items():
        price_key = (market_id, outcome)
        if price_key in market_prices:
            final_prices[price_key] = market_prices[price_key]
        else:
            final_prices[price_key] = position.avg_price
    
    # Calculate total portfolio value
    total_portfolio_value = portfolio.get_total_value(final_prices)
    total_profit = total_portfolio_value - initial_balance
    
    print("\n" + "=" * 80)
    print("📊 Final Portfolio Statistics:")
    print("=" * 80)
    print(f"Cash Balance: ${stats['balance']:.2f} USDC")
    print(f"Total Portfolio Value: ${total_portfolio_value:.2f} USDC")
    print(f"Total Profit: ${total_profit:+.2f} USDC ({total_profit/initial_balance*100:+.2f}%)")
    print(f"Total Trades: {stats['total_trades']}")
    print(f"Total Spent: ${stats['total_spent']:.2f} USDC")
    print(f"Open Positions: {stats['num_positions']}")
    
    if stats['num_positions'] > 0:
        # Group positions by market
        from polytrader.core.position import Position
        markets: dict[str, dict[Outcome, Position]] = {}
        for (market_id, outcome), position in portfolio.positions.items():
            if market_id not in markets:
                markets[market_id] = {}
            markets[market_id][outcome] = position
        
        print("\nPositions:")
        print(f"{'Market':<30} {'Direction':<10} {'Quantity':<12} {'Entry Price':<12} {'Current Price':<14}")
        print("-" * 78)
        
        for market_id, market_positions in markets.items():
            for outcome, position in market_positions.items():
                current_price = final_prices.get((market_id, outcome), position.avg_price)
                print(
                    f"{market_id:<30} {outcome:<10} {position.quantity:<12.4f} "
                    f"${position.avg_price:<11.4f} ${current_price:<13.4f}"
                )
        
        print("-" * 78)
        print("\nProfit by Market:")
        print(f"{'Market':<30} {'Profit if UP':<15} {'Profit if DOWN':<15}")
        print("-" * 60)
        
        total_profit_if_all_up = 0.0
        total_profit_if_all_down = 0.0
        
        for market_id, market_positions in markets.items():
            # Calculate total cost for all positions in this market
            total_cost = sum(
                pos.quantity * pos.avg_price
                for pos in market_positions.values()
            )
            
            # Calculate profit if UP wins
            up_position = market_positions.get("UP")
            down_position = market_positions.get("DOWN")
            up_value_if_up_wins = (up_position.quantity * 1.0) if up_position else 0.0
            down_value_if_up_wins = (down_position.quantity * 0.0) if down_position else 0.0
            profit_if_up = (up_value_if_up_wins + down_value_if_up_wins) - total_cost
            
            # Calculate profit if DOWN wins
            up_value_if_down_wins = (up_position.quantity * 0.0) if up_position else 0.0
            down_value_if_down_wins = (down_position.quantity * 1.0) if down_position else 0.0
            profit_if_down = (up_value_if_down_wins + down_value_if_down_wins) - total_cost
            
            total_profit_if_all_up += profit_if_up
            total_profit_if_all_down += profit_if_down
            
            print(f"{market_id:<30} ${profit_if_up:+14.2f} ${profit_if_down:+14.2f}")
        
        print("-" * 60)
        print(f"{'Total':<30} ${total_profit_if_all_up:+14.2f} ${total_profit_if_all_down:+14.2f}")
        
        # Calculate total portfolio value scenarios
        total_value_if_all_up = stats['balance'] + total_profit_if_all_up
        total_value_if_all_down = stats['balance'] + total_profit_if_all_down
        
        print(f"\nTotal Portfolio Value:")
        print(f"  If all UP outcomes win: ${total_value_if_all_up:.2f}")
        print(f"  If all DOWN outcomes win: ${total_value_if_all_down:.2f}")
    
    print("=" * 80)

