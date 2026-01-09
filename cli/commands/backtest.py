"""Backtest command handler."""

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from polytrader.core.manager import PortfolioManager
from polytrader.core.strategies import create_strategy
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
    asset: str  # Asset name extracted from market_id (e.g., "btc", "eth")


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


def extract_asset_from_market_id(market_id: str) -> str:
    """Extract asset name from market slug.
    
    Supports formats:
    - 15-minute: btc-updown-15m-{timestamp} or eth-updown-15m-{timestamp}
    - Hourly: bitcoin-up-or-down-{month}-{day}-{hour}am-et or ethereum-up-or-down-...
    
    Args:
        market_id: Market slug string
        
    Returns:
        Asset name in short format (e.g., "btc", "eth", "bitcoin", "ethereum")
    """
    market_id_lower = market_id.lower()
    
    # Check for 15-minute format: {asset}-updown-15m-{timestamp}
    if "-updown-15m-" in market_id_lower:
        asset = market_id_lower.split("-updown-15m-")[0]
        # Normalize common asset names
        if asset in ("bitcoin", "btc"):
            return "btc"
        elif asset in ("ethereum", "eth"):
            return "eth"
        return asset
    
    # Check for hourly format: {asset}-up-or-down-{month}-{day}-{hour}am-et
    if "-up-or-down-" in market_id_lower:
        asset = market_id_lower.split("-up-or-down-")[0]
        # Normalize to short format
        if asset == "bitcoin":
            return "btc"
        elif asset == "ethereum":
            return "eth"
        return asset
    
    # Fallback: try to extract from beginning of slug
    # Take first part before any hyphen
    parts = market_id_lower.split("-")
    if parts:
        asset = parts[0]
        if asset == "bitcoin":
            return "btc"
        elif asset == "ethereum":
            return "eth"
        return asset
    
    # Default to "unknown" if can't parse
    return "unknown"


def get_market_start_time(market_slug: str) -> float | None:
    """Extract start timestamp from market slug.
    
    For 15-minute markets: btc-updown-15m-{timestamp}
    Returns the start timestamp.
    
    Args:
        market_slug: Market slug string
        
    Returns:
        Start timestamp in seconds, or None if can't parse
    """
    if "-updown-15m-" in market_slug:
        try:
            timestamp_str = market_slug.split("-updown-15m-")[-1]
            start_timestamp = int(timestamp_str)
            return float(start_timestamp)
        except (ValueError, IndexError):
            return None
    
    return None


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


def filter_complete_markets(
    markets: dict[str, list[str]],
    verbose: bool = True,
) -> dict[str, list[str]]:
    """Filter markets to only include those that are complete (full 15 min).
    
    A market is considered complete if:
    - It's a 15-minute market
    - It has data covering the full 15-minute period (from start to expiration)
    - The latest tick timestamp is >= expiration time (meaning the market has fully expired)
    - The earliest tick timestamp is <= start time + small tolerance
    
    Args:
        markets: Dictionary mapping market slugs to CSV file paths
        verbose: Whether to print filtering messages (default: True)
        
    Returns:
        Dictionary of complete markets only
    """
    complete_markets: dict[str, list[str]] = {}
    
    if verbose:
        print(f"🔍 Filtering to complete (full 15 min) markets with full data coverage...")
    
    for market_id, csv_files in markets.items():
        start_time = get_market_start_time(market_id)
        expiration_time = get_market_expiration_time(market_id)
        
        if start_time is None or expiration_time is None:
            # Not a 15-minute market, skip
            continue
        
        # Load all ticks from all CSV files for this market
        all_ticks: list[MarketTick] = []
        for csv_file in csv_files:
            try:
                ticks = load_ticks_from_csv(csv_file)
                all_ticks.extend(ticks)
            except Exception:
                continue
        
        if not all_ticks:
            # No data for this market
            continue
        
        # Find earliest and latest tick timestamps
        earliest_tick = min(tick.ts for tick in all_ticks)
        latest_tick = max(tick.ts for tick in all_ticks)
        
        # Market duration in seconds (should be 900 seconds = 15 minutes)
        market_duration = expiration_time - start_time
        
        # Check that we have data covering the full 15-minute period:
        # 1. Latest tick should be >= expiration time (market has expired)
        # 2. Earliest tick should be <= start time + tolerance (data starts near beginning)
        # 3. Data span should cover at least 15 minutes (with small tolerance)
        data_span = latest_tick - earliest_tick
        
        # Tolerance: allow 5 seconds for timing variations
        tolerance = 5.0
        
        has_full_coverage = (
            latest_tick >= expiration_time - tolerance and
            earliest_tick <= start_time + tolerance and
            data_span >= market_duration - tolerance
        )
        
        if has_full_coverage:
            complete_markets[market_id] = csv_files
    
    if verbose:
        print(f"   Found {len(complete_markets)} complete markets with full 15 min data out of {len(markets)} total")
    return complete_markets


def get_last_n_markets(
    markets: dict[str, list[str]],
    n: int = 4,
) -> dict[str, list[str]]:
    """Get the last N markets sorted by start time.
    
    Args:
        markets: Dictionary mapping market slugs to CSV file paths
        n: Number of markets to return (default: 4)
        
    Returns:
        Dictionary of the last N markets
    """
    # Create list of (market_id, start_time) tuples
    market_times: list[tuple[str, float]] = []
    
    for market_id in markets.keys():
        start_time = get_market_start_time(market_id)
        if start_time is not None:
            market_times.append((market_id, start_time))
    
    # Sort by start time (ascending)
    market_times.sort(key=lambda x: x[1])
    
    # Take last N
    last_n = market_times[-n:] if len(market_times) > n else market_times
    
    # Build result dictionary
    result: dict[str, list[str]] = {}
    for market_id, _ in last_n:
        result[market_id] = markets[market_id]
    
    return result


def get_last_n_markets_per_asset(
    markets: dict[str, list[str]],
    n: int = 4,
) -> dict[str, list[str]]:
    """Get the last N complete markets for each asset.
    
    Groups markets by asset, filters to complete markets per asset,
    and returns the last N markets for each asset.
    
    Args:
        markets: Dictionary mapping market slugs to CSV file paths
        n: Number of markets to return per asset (default: 4)
        
    Returns:
        Dictionary of the last N markets for each asset
    """
    # Group markets by asset
    asset_markets: dict[str, dict[str, list[str]]] = defaultdict(dict)
    
    for market_id, csv_files in markets.items():
        asset = extract_asset_from_market_id(market_id)
        asset_markets[asset][market_id] = csv_files
    
    # Filter to complete markets and get last N for each asset
    result: dict[str, list[str]] = {}
    
    for asset, asset_market_dict in asset_markets.items():
        # Filter to complete markets for this asset (suppress verbose messages)
        complete_markets = filter_complete_markets(asset_market_dict, verbose=False)
        
        if not complete_markets:
            print(f"   ⚠️  {asset.upper()}: No complete markets found")
            continue
        
        # Get last N markets for this asset
        last_n = get_last_n_markets(complete_markets, n=n)
        
        # Add to result
        result.update(last_n)
        
        print(f"   ✓ {asset.upper()}: Selected {len(last_n)} complete markets (out of {len(complete_markets)} available)")
    
    return result


def backtest_market(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
    timestamp_tolerance: float = 0.1,
    timestamp_cutoff: float | None = None,
) -> BacktestResult:
    """Backtest a strategy on a single market.
    
    Args:
        market_id: Market identifier
        csv_files: List of CSV file paths for this market
        strategy_name: Name of strategy to use
        initial_balance: Starting balance in USDC
        timestamp_tolerance: Maximum timestamp difference for matching UP/DOWN ticks
        timestamp_cutoff: Only include ticks with timestamp >= this value (for filtering to time window)
        
    Returns:
        BacktestResult with performance metrics
    """
    # Load all ticks from all CSV files for this market
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)
    
    # Extract asset from market_id
    asset = extract_asset_from_market_id(market_id)
    
    # Filter ticks to only include those within the time window (if cutoff provided)
    if timestamp_cutoff is not None:
        all_ticks = [tick for tick in all_ticks if tick.ts >= timestamp_cutoff]
    
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
            asset=asset,
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
    
    # Helper function to calculate profit for both outcomes
    def calculate_profit_for_both_outcomes(market_id: str) -> tuple[float, float]:
        """Calculate profit if UP wins and if DOWN wins.
        
        Returns:
            Tuple of (profit_if_up_wins, profit_if_down_wins)
        """
        from polytrader.core.position import Position
        
        up_position = portfolio_manager.portfolio.get_position(market_id, "UP")
        down_position = portfolio_manager.portfolio.get_position(market_id, "DOWN")
        
        total_cost = (
            (up_position.quantity * up_position.avg_price if up_position else 0)
            + (down_position.quantity * down_position.avg_price if down_position else 0)
        )
        
        up_shares = up_position.quantity if up_position else 0
        down_shares = down_position.quantity if down_position else 0
        
        # If UP wins: we get $1.00 per UP share, $0.00 per DOWN share
        profit_if_up_wins = (up_shares * 1.0) - total_cost
        
        # If DOWN wins: we get $0.00 per UP share, $1.00 per DOWN share
        profit_if_down_wins = (down_shares * 1.0) - total_cost
        
        return (profit_if_up_wins, profit_if_down_wins)
    
    # Process ticks chronologically
    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None
    trade_number = 0
    
    print(f"\n📊 Trade-by-Trade Details for {market_id}:")
    print("-" * 180)
    print(f"{'#':<5} {'Timestamp':<12} {'Outcome':<8} {'Amount':<12} {'Shares':<10} {'Price':<10} {'If UP Wins':<15} {'If DOWN Wins':<15} {'Balance':<12}")
    print("-" * 180)
    
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
                    balance = portfolio_manager.get_balance()
                    
                    # Calculate profit for both outcomes after this trade
                    profit_if_up, profit_if_down = calculate_profit_for_both_outcomes(market_id)
                    
                    # Format timestamp for display
                    from datetime import datetime
                    timestamp_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3] if ts > 0 else "N/A"
                    
                    # Print trade details
                    if len(trades) > 1:
                        # Multiple trades (arbitrage - buying both sides)
                        total_shares = sum(t.amount / t.price for t in trades)
                        print(f"{trade_number:<5} {timestamp_str:<12} {'BOTH':<8} ${total_amount:<11.2f} "
                              f"{total_shares:<10.2f} {'N/A':<10} ${profit_if_up:<14.2f} ${profit_if_down:<14.2f} ${balance:<11.2f}")
                        # Print individual trades
                        for t in trades:
                            shares = t.amount / t.price if t.price > 0 else 0
                            print(f"     → {'':<12} {t.outcome:<6} ${t.amount:<11.2f} {shares:<10.2f} ${t.price:<9.4f}")
                    else:
                        # Single trade
                        trade = trades[0]
                        shares = trade.amount / trade.price if trade.price > 0 else 0
                        print(f"{trade_number:<5} {timestamp_str:<12} {trade.outcome:<8} ${trade.amount:<11.2f} "
                              f"{shares:<10.2f} ${trade.price:<9.4f} ${profit_if_up:<14.2f} ${profit_if_down:<14.2f} ${balance:<11.2f}")
    
    # Calculate guaranteed profit before settlement (for hedged positions)
    guaranteed_profit_before_settlement = calculate_guaranteed_profit(market_id)
    
    # Print summary after all trades
    if trade_number > 0:
        final_profit_if_up, final_profit_if_down = calculate_profit_for_both_outcomes(market_id)
        final_balance = portfolio_manager.get_balance()
        print("-" * 180)
        print(f"{'SUMMARY':<5} {'-':<12} {'-':<8} ${portfolio_manager.total_spent:<11.2f} "
              f"{'Total':<10} {'-':<10} ${final_profit_if_up:<14.2f} ${final_profit_if_down:<14.2f} ${final_balance:<11.2f}")
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
        
        # Print final outcome (using positions before settlement)
        if trade_number > 0:
            up_shares = up_position_before.quantity if up_position_before else 0
            down_shares = down_position_before.quantity if down_position_before else 0
            
            # Calculate profit for both outcomes using positions before settlement
            profit_if_up_wins = (up_shares * 1.0) - total_cost_before_settlement
            profit_if_down_wins = (down_shares * 1.0) - total_cost_before_settlement
            
            print(f"🏁 FINAL OUTCOME: {winner} WINS")
            if winner == "UP":
                print(f"   Profit if UP wins: ${profit_if_up_wins:.2f} ✅ (ACTUAL)")
                print(f"   Profit if DOWN wins: ${profit_if_down_wins:.2f}")
            else:
                print(f"   Profit if UP wins: ${profit_if_up_wins:.2f}")
                print(f"   Profit if DOWN wins: ${profit_if_down_wins:.2f} ✅ (ACTUAL)")
            print()
    
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
        asset=asset,
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
    
    # Profit by asset
    asset_results: dict[str, list[BacktestResult]] = defaultdict(list)
    for result in results:
        asset_results[result.asset].append(result)
    
    if len(asset_results) > 1:
        print(f"\n💰 PROFIT BY ASSET:")
        print("=" * 120)
        print(f"{'Asset':<20} {'Markets':<10} {'Initial':<12} {'Final':<12} {'Actual Profit':<14} {'Guaranteed':<12} {'Profit %':<10} {'Trades':<8}")
        print("-" * 120)
        
        for asset in sorted(asset_results.keys()):
            asset_result_list = asset_results[asset]
            asset_initial = sum(r.initial_balance for r in asset_result_list)
            asset_final = sum(r.final_balance for r in asset_result_list)
            asset_profit = asset_final - asset_initial
            asset_actual_profit = sum(r.actual_profit for r in asset_result_list)
            asset_guaranteed_profit = sum(r.guaranteed_profit for r in asset_result_list)
            asset_profit_pct = (asset_profit / asset_initial * 100) if asset_initial > 0 else 0.0
            asset_trades = sum(r.total_trades for r in asset_result_list)
            
            print(f"{asset.upper():<20} {len(asset_result_list):<10} ${asset_initial:<11.2f} ${asset_final:<11.2f} "
                  f"${asset_actual_profit:<13.2f} ${asset_guaranteed_profit:<11.2f} {asset_profit_pct:<9.2f}% {asset_trades:<8}")
        
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


def backtest_mode(args: argparse.Namespace) -> None:
    """Run backtest mode."""
    print(f"🔍 Finding market data in '{args.data_dir}'...")
    markets = find_all_data_files(args.data_dir)
    
    if not markets:
        print(f"❌ No market data found in '{args.data_dir}'")
        return
    
    print(f"📊 Found {len(markets)} markets")
    
    # Filter to specific market if requested
    market_cutoffs: dict[str, float] = {}
    if args.market:
        if args.market in markets:
            markets = {args.market: markets[args.market]}
            print(f"🎯 Backtesting only market: {args.market}")
            # No time filtering for specific market
        else:
            print(f"❌ Market '{args.market}' not found in data")
            return
    else:
        # Filter to complete markets (full 15 min) and get last 4 per asset
        print(f"🔍 Filtering to complete (full 15 min) markets with full data coverage per asset...")
        markets = get_last_n_markets_per_asset(markets, n=4)
        if not markets:
            print(f"❌ No complete markets found for any asset")
            return
        
        print(f"📊 Selected last 4 complete markets per asset (total: {len(markets)} markets) for backtesting")
    
    # Run backtests
    results: list[BacktestResult] = []
    
    for market_id, csv_files in sorted(markets.items()):
        print(f"\n📈 Backtesting {market_id}...")
        print(f"   Found {len(csv_files)} data file(s)")
        
        # Get cutoff timestamp for this market (if filtering is enabled)
        timestamp_cutoff = market_cutoffs.get(market_id)
        
        result = backtest_market(
            market_id=market_id,
            csv_files=csv_files,
            strategy_name=args.strategy,
            initial_balance=args.initial_balance,
            timestamp_tolerance=args.timestamp_tolerance,
            timestamp_cutoff=timestamp_cutoff,
        )
        
        results.append(result)
        print(f"   ✅ Completed: {result.total_trades} trades, "
              f"${result.profit:+.2f} profit ({result.profit_pct:+.2f}%)")
    
    # Print summary
    print_results(results)

