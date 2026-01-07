#!/usr/bin/env python3
"""Backtest trading strategies on historical market data.

This script processes all CSV files in the ./data directory and runs backtests
on each market, simulating trades based on the strategy's decisions.
"""

import argparse
import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from polytrader.core.manager import PortfolioManager
from polytrader.core.strategy_registry import create_strategy
from polytrader.types import MarketTick, Outcome


@dataclass
class BacktestResult:
    """Results from a single market backtest."""
    market_id: str
    initial_balance: float
    final_balance: float
    total_trades: int
    total_spent: float
    positions_settled: int
    total_payout: float
    winner: str | None
    profit: float
    profit_pct: float
    guaranteed_profit: float  # Guaranteed profit from hedged positions before settlement
    actual_profit: float  # Actual profit after settlement


def find_all_data_files(data_dir: str = "data") -> dict[str, list[str]]:
    """Find all CSV data files, grouped by market slug.
    
    Args:
        data_dir: Directory containing market data
        
    Returns:
        Dictionary mapping market slugs to list of CSV file paths
    """
    markets: dict[str, list[str]] = defaultdict(list)
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"⚠️  Data directory '{data_dir}' not found")
        return markets
    
    # Walk through data directory structure: data/{market-slug}/{date}/{time}/data.csv
    for market_dir in data_path.iterdir():
        if not market_dir.is_dir():
            continue
            
        market_slug = market_dir.name
        
        # Find all CSV files in this market's subdirectories
        for csv_file in market_dir.rglob("data.csv"):
            markets[market_slug].append(str(csv_file))
    
    return markets


def load_ticks_from_csv(csv_path: str) -> list[MarketTick]:
    """Load market ticks from a CSV file.
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        List of MarketTick objects sorted by timestamp
    """
    ticks: list[MarketTick] = []
    
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                tick = MarketTick(
                    ts=float(row["timestamp"]),
                    market_id=row["market_slug"],
                    outcome=row["outcome"],  # type: ignore
                    best_bid=float(row["best_bid"]),
                    best_ask=float(row["best_ask"]),
                )
                ticks.append(tick)
            except (ValueError, KeyError) as e:
                print(f"⚠️  Skipping invalid row in {csv_path}: {e}")
                continue
    
    # Sort by timestamp
    ticks.sort(key=lambda t: t.ts)
    return ticks


def get_market_expiration_time(market_slug: str) -> float | None:
    """Extract expiration timestamp from market slug.
    
    For 15-minute markets: btc-updown-15m-{timestamp}
    Returns the timestamp + 15 minutes (900 seconds).
    
    Args:
        market_slug: Market slug string
        
    Returns:
        Expiration timestamp in seconds, or None if can't parse
    """
    if "-updown-15m-" in market_slug:
        try:
            timestamp_str = market_slug.split("-updown-15m-")[-1]
            start_timestamp = int(timestamp_str)
            # 15-minute markets expire 15 minutes (900 seconds) after start
            return float(start_timestamp + 900)
        except (ValueError, IndexError):
            return None
    
    # For other market types, we'd need more logic
    # For now, return None (markets won't expire in backtest)
    return None


def backtest_market(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
    timestamp_tolerance: float = 0.1,
) -> BacktestResult:
    """Backtest a strategy on a single market.
    
    Args:
        market_id: Market identifier
        csv_files: List of CSV file paths for this market
        strategy_name: Name of strategy to use
        initial_balance: Starting balance in USDC
        timestamp_tolerance: Maximum timestamp difference for matching UP/DOWN ticks
        
    Returns:
        BacktestResult with performance metrics
    """
    # Load all ticks from all CSV files for this market
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)
    
    if not all_ticks:
        return BacktestResult(
            market_id=market_id,
            initial_balance=initial_balance,
            final_balance=initial_balance,
            total_trades=0,
            total_spent=0.0,
            positions_settled=0,
            total_payout=0.0,
            winner=None,
            profit=0.0,
            profit_pct=0.0,
            guaranteed_profit=0.0,
            actual_profit=0.0,
        )
    
    # Sort all ticks by timestamp
    all_ticks.sort(key=lambda t: t.ts)
    
    # Initialize portfolio manager with strategy
    strategy = create_strategy(strategy_name)
    portfolio_manager = PortfolioManager(
        initial_balance=initial_balance,
        strategy=strategy,
    )
    
    # Group ticks by timestamp (within tolerance)
    # We need to process ticks and match UP/DOWN pairs with matching timestamps
    tick_groups: dict[float, dict[Outcome, MarketTick]] = defaultdict(dict)
    
    for tick in all_ticks:
        # Round timestamp to nearest 0.1s for grouping
        rounded_ts = round(tick.ts, 1)
        tick_groups[rounded_ts][tick.outcome] = tick
    
    # Helper function to calculate guaranteed profit
    def calculate_guaranteed_profit(market_id: str) -> float:
        """Calculate guaranteed profit (net arbitrage profit) for current positions."""
        from polytrader.core.position import Position
        
        up_position = portfolio_manager.portfolio.get_position(market_id, "UP")
        down_position = portfolio_manager.portfolio.get_position(market_id, "DOWN")
        
        total_cost = (
            (up_position.quantity * up_position.avg_price if up_position else 0)
            + (down_position.quantity * down_position.avg_price if down_position else 0)
        )
        
        up_shares = up_position.quantity if up_position else 0
        down_shares = down_position.quantity if down_position else 0
        
        # Guaranteed profit = minimum shares * $1.00 - total cost
        guaranteed_profit = min(up_shares, down_shares) * 1.0 - total_cost
        return guaranteed_profit
    
    # Process ticks chronologically
    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None
    trade_number = 0
    
    print(f"\n📊 Trade-by-Trade Details for {market_id}:")
    print("-" * 140)
    print(f"{'#':<5} {'Timestamp':<12} {'Outcome':<8} {'Amount':<12} {'Shares':<10} {'Price':<10} {'Profit Before':<15} {'Profit After':<15} {'Balance':<12}")
    print("-" * 140)
    
    for ts in processed_timestamps:
        group = tick_groups[ts]
        
        # Update latest ticks for each outcome
        if "UP" in group:
            latest_up_tick = group["UP"]
        if "DOWN" in group:
            latest_down_tick = group["DOWN"]
        
        # Only trade when we have both UP and DOWN with matching timestamps
        if latest_up_tick and latest_down_tick:
            # Check if timestamps match (within tolerance)
            timestamp_diff = abs(latest_up_tick.ts - latest_down_tick.ts)
            if timestamp_diff <= timestamp_tolerance:
                # Calculate profit before trade
                profit_before = calculate_guaranteed_profit(market_id)
                
                # Process prices for trading decision (use the timestamp from ticks)
                decision = portfolio_manager.process_prices(
                    market_id=market_id,
                    up_price=latest_up_tick.best_ask,
                    down_price=latest_down_tick.best_ask,
                    timestamp=ts,  # Pass the backtest timestamp
                )
                
                # If trades were executed, print details
                if decision:
                    # Handle both single trade and list of trades
                    trades = decision if isinstance(decision, list) else [decision]
                    
                    trade_number += 1
                    total_amount = sum(t.amount for t in trades)
                    profit_after = calculate_guaranteed_profit(market_id)
                    balance = portfolio_manager.get_balance()
                    
                    # Format timestamp for display
                    from datetime import datetime
                    timestamp_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3] if ts > 0 else "N/A"
                    
                    # Print trade details
                    if len(trades) > 1:
                        # Multiple trades (arbitrage - buying both sides)
                        total_shares = sum(t.amount / t.price for t in trades)
                        print(f"{trade_number:<5} {timestamp_str:<12} {'BOTH':<8} ${total_amount:<11.2f} "
                              f"{total_shares:<10.2f} {'N/A':<10} ${profit_before:<14.2f} ${profit_after:<14.2f} ${balance:<11.2f}")
                        # Print individual trades
                        for t in trades:
                            shares = t.amount / t.price if t.price > 0 else 0
                            print(f"     → {'':<12} {t.outcome:<6} ${t.amount:<11.2f} {shares:<10.2f} ${t.price:<9.4f}")
                    else:
                        # Single trade
                        trade = trades[0]
                        shares = trade.amount / trade.price if trade.price > 0 else 0
                        print(f"{trade_number:<5} {timestamp_str:<12} {trade.outcome:<8} ${trade.amount:<11.2f} "
                              f"{shares:<10.2f} ${trade.price:<9.4f} ${profit_before:<14.2f} ${profit_after:<14.2f} ${balance:<11.2f}")
    
    # Calculate guaranteed profit before settlement (for hedged positions)
    guaranteed_profit_before_settlement = calculate_guaranteed_profit(market_id)
    
    # Print summary after all trades
    if trade_number > 0:
        final_profit = calculate_guaranteed_profit(market_id)
        final_balance = portfolio_manager.get_balance()
        print("-" * 140)
        print(f"{'SUMMARY':<5} {'-':<12} {'-':<8} ${portfolio_manager.total_spent:<11.2f} "
              f"{'Total':<10} {'-':<10} ${final_profit:<14.2f} ${final_balance:<11.2f}")
        print()
    
    # Settle positions at market expiration
    expiration_time = get_market_expiration_time(market_id)
    winner: str | None = None
    positions_settled = 0
    total_payout = 0.0
    
    # Get positions before settlement to calculate actual profit
    from polytrader.core.position import Position
    up_position_before = portfolio_manager.portfolio.get_position(market_id, "UP")
    down_position_before = portfolio_manager.portfolio.get_position(market_id, "DOWN")
    
    total_cost_before_settlement = (
        (up_position_before.quantity * up_position_before.avg_price if up_position_before else 0)
        + (down_position_before.quantity * down_position_before.avg_price if down_position_before else 0)
    )
    
    if expiration_time and latest_up_tick and latest_down_tick:
        # Use final prices to determine winner
        final_up_price = latest_up_tick.best_ask
        final_down_price = latest_down_tick.best_ask
        
        settlement = portfolio_manager.expire_positions(
            market_id=market_id,
            up_price=final_up_price,
            down_price=final_down_price,
        )
        winner = settlement["winner"]
        positions_settled = settlement["positions_settled"]
        total_payout = settlement["total_payout"]
    
    # Calculate actual profit after settlement
    # Actual profit = payout from winning positions - total cost
    # For hedged positions: if we have both UP and DOWN, we get min(UP_shares, DOWN_shares) * $1.00
    # For unhedged positions: we only get payout if our position wins
    if up_position_before and down_position_before:
        # Hedged position: guaranteed profit is min(UP, DOWN) * $1.00 - total_cost
        up_shares = up_position_before.quantity
        down_shares = down_position_before.quantity
        hedged_shares = min(up_shares, down_shares)
        
        # Actual payout depends on winner
        if winner == "UP":
            # UP wins: we get $1.00 per UP share, $0.00 per DOWN share
            actual_payout = up_shares * 1.0
        else:  # DOWN wins
            # DOWN wins: we get $0.00 per UP share, $1.00 per DOWN share
            actual_payout = down_shares * 1.0
        
        # Actual profit = actual payout - total cost
        actual_profit = actual_payout - total_cost_before_settlement
    elif up_position_before:
        # Only UP position
        up_shares = up_position_before.quantity
        actual_payout = up_shares * 1.0 if winner == "UP" else 0.0
        actual_profit = actual_payout - total_cost_before_settlement
    elif down_position_before:
        # Only DOWN position
        down_shares = down_position_before.quantity
        actual_payout = down_shares * 1.0 if winner == "DOWN" else 0.0
        actual_profit = actual_payout - total_cost_before_settlement
    else:
        # No positions
        actual_profit = 0.0
    
    # Calculate final statistics
    stats = portfolio_manager.get_statistics()
    final_balance = stats["balance"]
    profit = final_balance - initial_balance  # This is the same as actual_profit, but calculated from balance
    profit_pct = (profit / initial_balance * 100) if initial_balance > 0 else 0.0
    
    return BacktestResult(
        market_id=market_id,
        initial_balance=initial_balance,
        final_balance=final_balance,
        total_trades=stats["total_trades"],
        total_spent=stats["total_spent"],
        positions_settled=positions_settled,
        total_payout=total_payout,
        winner=winner,
        profit=profit,
        profit_pct=profit_pct,
        guaranteed_profit=guaranteed_profit_before_settlement,
        actual_profit=actual_profit,
    )


def print_results(results: list[BacktestResult]) -> None:
    """Print backtest results in a formatted table."""
    if not results:
        print("No results to display")
        return
    
    print("\n" + "=" * 100)
    print("BACKTEST RESULTS")
    print("=" * 100)
    
    # Header
    print(f"{'Market':<40} {'Initial':<12} {'Final':<12} {'Actual Profit':<14} {'Guaranteed':<12} {'Profit %':<10} {'Trades':<8} {'Winner':<8}")
    print("-" * 120)
    
    # Individual market results
    for result in results:
        winner_str = result.winner or "N/A"
        print(
            f"{result.market_id:<40} "
            f"${result.initial_balance:<11.2f} "
            f"${result.final_balance:<11.2f} "
            f"${result.actual_profit:<13.2f} "
            f"${result.guaranteed_profit:<11.2f} "
            f"{result.profit_pct:<9.2f}% "
            f"{result.total_trades:<8} "
            f"{winner_str:<8}"
        )
    
    # Summary statistics
    print("-" * 120)
    total_initial = sum(r.initial_balance for r in results)
    total_final = sum(r.final_balance for r in results)
    total_profit = total_final - total_initial
    total_actual_profit = sum(r.actual_profit for r in results)
    total_guaranteed_profit = sum(r.guaranteed_profit for r in results)
    total_profit_pct = (total_profit / total_initial * 100) if total_initial > 0 else 0.0
    total_trades = sum(r.total_trades for r in results)
    total_spent = sum(r.total_spent for r in results)
    
    print(f"{'TOTAL':<40} ${total_initial:<11.2f} ${total_final:<11.2f} ${total_actual_profit:<13.2f} ${total_guaranteed_profit:<11.2f} {total_profit_pct:<9.2f}% {total_trades:<8}")
    print("=" * 120)
    
    # Additional metrics
    print(f"\n📊 SUMMARY STATISTICS:")
    print(f"{'Total Markets:':<25} {len(results)}")
    print(f"{'Total Trades:':<25} {total_trades}")
    print(f"{'Total Spent:':<25} ${total_spent:.2f}")
    print(f"{'Total Initial Balance:':<25} ${total_initial:.2f}")
    print(f"{'Total Final Balance:':<25} ${total_final:.2f}")
    print(f"{'💰 TOTAL ACTUAL PROFIT:':<25} ${total_actual_profit:+.2f} ({total_profit_pct:+.2f}%)")
    print(f"{'💰 TOTAL GUARANTEED PROFIT:':<25} ${total_guaranteed_profit:+.2f}")
    print(f"{'Average Actual Profit per Market:':<25} ${total_actual_profit / len(results):+.2f}")
    print(f"{'Average Guaranteed Profit per Market:':<25} ${total_guaranteed_profit / len(results):+.2f}")
    print(f"{'Win Rate (Actual):':<25} {sum(1 for r in results if r.actual_profit > 0) / len(results) * 100:.1f}%")
    
    # Markets with positions settled
    settled_markets = [r for r in results if r.positions_settled > 0]
    if settled_markets:
        print(f"\nMarkets with Settled Positions: {len(settled_markets)}")
        for result in settled_markets:
            print(f"  {result.market_id}: {result.positions_settled} positions, "
                  f"Winner: {result.winner}, Payout: ${result.total_payout:.2f}")


def main() -> None:
    """Main backtest function."""
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies on historical market data"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="arbitrage",
        help="Strategy to backtest (default: arbitrage)",
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=1000.0,
        help="Initial balance in USDC (default: 1000.0)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Directory containing market data (default: data)",
    )
    parser.add_argument(
        "--timestamp-tolerance",
        type=float,
        default=0.1,
        help="Maximum timestamp difference for matching UP/DOWN ticks in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Backtest only a specific market slug (default: all markets)",
    )
    
    args = parser.parse_args()
    
    print(f"🔍 Finding market data in '{args.data_dir}'...")
    markets = find_all_data_files(args.data_dir)
    
    if not markets:
        print(f"❌ No market data found in '{args.data_dir}'")
        return
    
    print(f"📊 Found {len(markets)} markets")
    
    # Filter to specific market if requested
    if args.market:
        if args.market in markets:
            markets = {args.market: markets[args.market]}
            print(f"🎯 Backtesting only market: {args.market}")
        else:
            print(f"❌ Market '{args.market}' not found in data")
            return
    
    # Run backtests
    results: list[BacktestResult] = []
    
    for market_id, csv_files in sorted(markets.items()):
        print(f"\n📈 Backtesting {market_id}...")
        print(f"   Found {len(csv_files)} data file(s)")
        
        result = backtest_market(
            market_id=market_id,
            csv_files=csv_files,
            strategy_name=args.strategy,
            initial_balance=args.initial_balance,
            timestamp_tolerance=args.timestamp_tolerance,
        )
        
        results.append(result)
        print(f"   ✅ Completed: {result.total_trades} trades, "
              f"${result.profit:+.2f} profit ({result.profit_pct:+.2f}%)")
    
    # Print summary
    print_results(results)


if __name__ == "__main__":
    main()

