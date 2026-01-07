#!/usr/bin/env python3
"""Benchmark different parameter combinations for GabagoolStrategy.

This script tests various parameter combinations and compares their performance
on historical backtest data.
"""

import argparse
import csv
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from polytrader.core.manager import PortfolioManager
from polytrader.core.strategy import GabagoolStrategy
from polytrader.types import MarketTick, Outcome


@dataclass
class ParameterSet:
    """A set of parameters to test."""
    accumulate_price: float
    hedge_price: float
    max_accumulate_price: float
    max_buy_price: float
    max_ratio: float
    min_arbitrage_pair_cost: float
    max_order_size: float
    min_trade_size: float
    min_seconds_between_trades: float
    max_capital_per_market: float
    max_loss_threshold: float


@dataclass
class BenchmarkResult:
    """Results from benchmarking a parameter set."""
    params: ParameterSet
    total_profit: float
    total_profit_pct: float
    total_trades: int
    total_spent: float
    markets_tested: int
    win_rate: float
    avg_profit_per_market: float


def find_all_data_files(data_dir: str = "data") -> dict[str, list[str]]:
    """Find all CSV data files, grouped by market slug."""
    markets: dict[str, list[str]] = defaultdict(list)
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"⚠️  Data directory '{data_dir}' not found")
        return markets
    
    for market_dir in data_path.iterdir():
        if not market_dir.is_dir():
            continue
            
        market_slug = market_dir.name
        
        for csv_file in market_dir.rglob("data.csv"):
            markets[market_slug].append(str(csv_file))
    
    return markets


def load_ticks_from_csv(csv_path: str) -> list[MarketTick]:
    """Load market ticks from a CSV file."""
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
                continue
    
    ticks.sort(key=lambda t: t.ts)
    return ticks


def get_market_expiration_time(market_slug: str) -> float | None:
    """Extract expiration timestamp from market slug."""
    if "-updown-15m-" in market_slug:
        try:
            timestamp_str = market_slug.split("-updown-15m-")[-1]
            start_timestamp = int(timestamp_str)
            return float(start_timestamp + 900)
        except (ValueError, IndexError):
            return None
    return None


def calculate_guaranteed_profit(portfolio_manager: PortfolioManager, market_id: str) -> float:
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
    
    guaranteed_profit = min(up_shares, down_shares) * 1.0 - total_cost
    return guaranteed_profit


def backtest_market_with_params(
    market_id: str,
    csv_files: list[str],
    params: ParameterSet,
    initial_balance: float,
    timestamp_tolerance: float = 0.1,
    verbose: bool = False,
) -> dict[str, Any]:
    """Backtest a strategy with specific parameters on a single market."""
    # Load all ticks
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)
    
    if not all_ticks:
        return {
            "market_id": market_id,
            "profit": 0.0,
            "profit_pct": 0.0,
            "total_trades": 0,
            "total_spent": 0.0,
            "positions_settled": 0,
            "total_payout": 0.0,
            "guaranteed_profit": 0.0,
            "actual_profit": 0.0,
        }
    
    all_ticks.sort(key=lambda t: t.ts)
    
    # Create strategy with parameters
    strategy = GabagoolStrategy(
        accumulate_price=params.accumulate_price,
        hedge_price=params.hedge_price,
        max_accumulate_price=params.max_accumulate_price,
        max_buy_price=params.max_buy_price,
        max_ratio=params.max_ratio,
        min_arbitrage_pair_cost=params.min_arbitrage_pair_cost,
        max_order_size=params.max_order_size,
        min_trade_size=params.min_trade_size,
        min_seconds_between_trades=params.min_seconds_between_trades,
        max_capital_per_market=params.max_capital_per_market,
        max_loss_threshold=params.max_loss_threshold,
    )
    
    portfolio_manager = PortfolioManager(
        initial_balance=initial_balance,
        strategy=strategy,
    )
    
    # Group ticks by timestamp
    tick_groups: dict[float, dict[Outcome, MarketTick]] = defaultdict(dict)
    for tick in all_ticks:
        rounded_ts = round(tick.ts, 1)
        tick_groups[rounded_ts][tick.outcome] = tick
    
    # Process ticks chronologically
    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None
    
    for ts in processed_timestamps:
        group = tick_groups[ts]
        
        if "UP" in group:
            latest_up_tick = group["UP"]
        if "DOWN" in group:
            latest_down_tick = group["DOWN"]
        
        if latest_up_tick and latest_down_tick:
            timestamp_diff = abs(latest_up_tick.ts - latest_down_tick.ts)
            if timestamp_diff <= timestamp_tolerance:
                portfolio_manager.process_prices(
                    market_id=market_id,
                    up_price=latest_up_tick.best_ask,
                    down_price=latest_down_tick.best_ask,
                    timestamp=ts,
                )
    
    # Calculate guaranteed profit before settlement
    guaranteed_profit_before_settlement = calculate_guaranteed_profit(portfolio_manager, market_id)
    
    # Get positions before settlement to calculate actual profit
    from polytrader.core.position import Position
    up_position_before = portfolio_manager.portfolio.get_position(market_id, "UP")
    down_position_before = portfolio_manager.portfolio.get_position(market_id, "DOWN")
    
    total_cost_before_settlement = (
        (up_position_before.quantity * up_position_before.avg_price if up_position_before else 0)
        + (down_position_before.quantity * down_position_before.avg_price if down_position_before else 0)
    )
    
    # Settle positions at market expiration
    expiration_time = get_market_expiration_time(market_id)
    positions_settled = 0
    total_payout = 0.0
    winner: str | None = None
    
    if expiration_time and latest_up_tick and latest_down_tick:
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
    if up_position_before and down_position_before:
        # Hedged position
        up_shares = up_position_before.quantity
        down_shares = down_position_before.quantity
        
        if winner == "UP":
            actual_payout = up_shares * 1.0
        elif winner == "DOWN":
            actual_payout = down_shares * 1.0
        else:
            actual_payout = 0.0
        
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
    profit = final_balance - initial_balance  # This equals actual_profit
    profit_pct = (profit / initial_balance * 100) if initial_balance > 0 else 0.0
    
    return {
        "market_id": market_id,
        "profit": profit,
        "profit_pct": profit_pct,
        "total_trades": stats["total_trades"],
        "total_spent": stats["total_spent"],
        "positions_settled": positions_settled,
        "total_payout": total_payout,
        "guaranteed_profit": guaranteed_profit_before_settlement,
        "actual_profit": actual_profit,
    }


def benchmark_parameter_set(
    params: ParameterSet,
    markets: dict[str, list[str]],
    initial_balance: float,
    timestamp_tolerance: float = 0.1,
    verbose: bool = False,
) -> BenchmarkResult:
    """Benchmark a single parameter set across all markets."""
    results: list[dict[str, Any]] = []
    
    for market_id, csv_files in markets.items():
        result = backtest_market_with_params(
            market_id=market_id,
            csv_files=csv_files,
            params=params,
            initial_balance=initial_balance,
            timestamp_tolerance=timestamp_tolerance,
            verbose=verbose,
        )
        results.append(result)
    
    # Aggregate results - use actual_profit for calculations
    total_profit = sum(r.get("actual_profit", r["profit"]) for r in results)
    total_guaranteed_profit = sum(r.get("guaranteed_profit", 0.0) for r in results)
    total_profit_pct = (total_profit / (initial_balance * len(results)) * 100) if results else 0.0
    total_trades = sum(r["total_trades"] for r in results)
    total_spent = sum(r["total_spent"] for r in results)
    markets_tested = len(results)
    win_rate = sum(1 for r in results if r.get("actual_profit", r["profit"]) > 0) / markets_tested if markets_tested > 0 else 0.0
    avg_profit_per_market = total_profit / markets_tested if markets_tested > 0 else 0.0
    
    return BenchmarkResult(
        params=params,
        total_profit=total_profit,
        total_profit_pct=total_profit_pct,
        total_trades=total_trades,
        total_spent=total_spent,
        markets_tested=markets_tested,
        win_rate=win_rate,
        avg_profit_per_market=avg_profit_per_market,
    )


def generate_parameter_combinations(
    base_params: ParameterSet,
    param_ranges: dict[str, list[float]],
) -> list[ParameterSet]:
    """Generate all combinations of parameters to test.
    
    Args:
        base_params: Base parameter set (default values)
        param_ranges: Dictionary mapping parameter names to lists of values to test
        
    Returns:
        List of ParameterSet objects to test
    """
    # Get all parameter names that have ranges defined
    param_names = list(param_ranges.keys())
    param_values = [param_ranges[name] for name in param_names]
    
    combinations = []
    
    # Generate all combinations
    for combo in itertools.product(*param_values):
        # Start with base params
        param_dict = asdict(base_params)
        
        # Override with combination values
        for name, value in zip(param_names, combo):
            param_dict[name] = value
        
        combinations.append(ParameterSet(**param_dict))
    
    return combinations


def print_results(results: list[BenchmarkResult], top_n: int = 10) -> None:
    """Print benchmark results in a formatted table."""
    if not results:
        print("No results to display")
        return
    
    # Sort by total profit (descending)
    sorted_results = sorted(results, key=lambda r: r.total_profit, reverse=True)
    
    print("\n" + "=" * 150)
    print("PARAMETER BENCHMARK RESULTS")
    print("=" * 150)
    
    # Print top N results
    print(f"\n📊 Top {top_n} Parameter Combinations (by Total Profit):")
    print("-" * 150)
    
    # Header
    header = (
        f"{'Rank':<6} "
        f"{'Profit':<12} "
        f"{'Profit %':<12} "
        f"{'Trades':<8} "
        f"{'Win Rate':<10} "
        f"{'Accum':<8} "
        f"{'Hedge':<8} "
        f"{'Max Acc':<8} "
        f"{'Max Buy':<8} "
        f"{'Max Ratio':<10} "
        f"{'Min Arb':<8} "
        f"{'Max Cap':<10} "
        f"{'Loss Thresh':<12}"
    )
    print(header)
    print("-" * 150)
    
    for i, result in enumerate(sorted_results[:top_n], 1):
        p = result.params
        print(
            f"{i:<6} "
            f"${result.total_profit:<11.2f} "
            f"{result.total_profit_pct:<11.2f}% "
            f"{result.total_trades:<8} "
            f"{result.win_rate*100:<9.1f}% "
            f"{p.accumulate_price:<8.2f} "
            f"{p.hedge_price:<8.2f} "
            f"{p.max_accumulate_price:<8.2f} "
            f"{p.max_buy_price:<8.2f} "
            f"{p.max_ratio:<10.2f} "
            f"{p.min_arbitrage_pair_cost:<8.2f} "
            f"${p.max_capital_per_market:<9.0f} "
            f"${p.max_loss_threshold:<11.0f}"
        )
    
    print("=" * 150)
    
    # Print worst performers
    print(f"\n📉 Bottom {min(5, len(sorted_results))} Parameter Combinations:")
    print("-" * 150)
    print(header)
    print("-" * 150)
    
    for i, result in enumerate(sorted_results[-5:], len(sorted_results) - 4):
        p = result.params
        print(
            f"{i:<6} "
            f"${result.total_profit:<11.2f} "
            f"{result.total_profit_pct:<11.2f}% "
            f"{result.total_trades:<8} "
            f"{result.win_rate*100:<9.1f}% "
            f"{p.accumulate_price:<8.2f} "
            f"{p.hedge_price:<8.2f} "
            f"{p.max_accumulate_price:<8.2f} "
            f"{p.max_buy_price:<8.2f} "
            f"{p.max_ratio:<10.2f} "
            f"{p.min_arbitrage_pair_cost:<8.2f} "
            f"${p.max_capital_per_market:<9.0f} "
            f"${p.max_loss_threshold:<11.0f}"
        )
    
    print("=" * 150)
    
    # Summary statistics
    print(f"\n📈 Summary Statistics:")
    print(f"{'Total Combinations Tested:':<30} {len(results)}")
    print(f"{'Best Profit:':<30} ${sorted_results[0].total_profit:.2f}")
    print(f"{'Worst Profit:':<30} ${sorted_results[-1].total_profit:.2f}")
    print(f"{'Average Profit:':<30} ${sum(r.total_profit for r in results) / len(results):.2f}")
    print(f"{'Median Profit:':<30} ${sorted_results[len(sorted_results)//2].total_profit:.2f}")


def save_results_to_json(results: list[BenchmarkResult], output_file: str) -> None:
    """Save benchmark results to a JSON file."""
    results_dict = [
        {
            "params": asdict(result.params),
            "total_profit": result.total_profit,
            "total_profit_pct": result.total_profit_pct,
            "total_trades": result.total_trades,
            "total_spent": result.total_spent,
            "markets_tested": result.markets_tested,
            "win_rate": result.win_rate,
            "avg_profit_per_market": result.avg_profit_per_market,
        }
        for result in results
    ]
    
    with open(output_file, "w") as f:
        json.dump(results_dict, f, indent=2)
    
    print(f"\n💾 Results saved to {output_file}")


def main() -> None:
    """Main benchmarking function."""
    parser = argparse.ArgumentParser(
        description="Benchmark different parameter combinations for GabagoolStrategy"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Directory containing market data (default: data)",
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=1000.0,
        help="Initial balance in USDC (default: 1000.0)",
    )
    parser.add_argument(
        "--timestamp-tolerance",
        type=float,
        default=0.1,
        help="Maximum timestamp difference for matching UP/DOWN ticks (default: 0.1)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="benchmark_results.json",
        help="Output JSON file for results (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top results to display (default: 10)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output for each market",
    )
    
    args = parser.parse_args()
    
    # Base parameters (from strategy_registry.py lines 25-37)
    base_params = ParameterSet(
        accumulate_price=0.60,
        hedge_price=0.33,
        max_accumulate_price=0.63,
        max_buy_price=0.9,
        max_ratio=1.4,
        min_arbitrage_pair_cost=0.92,
        max_order_size=20.0,
        min_trade_size=2.0,
        min_seconds_between_trades=20.0,
        max_capital_per_market=150.0,
        max_loss_threshold=10.0,
    )
    
    # Define parameter ranges to test
    # You can modify these to test different ranges
    param_ranges: dict[str, list[float]] = {
        # Test accumulate_price around 0.60
        "accumulate_price": [0.58, 0.60, 0.62],
        
        # Test hedge_price around 0.33
        "hedge_price": [0.30, 0.33, 0.35],
        
        # Test max_accumulate_price around 0.63
        "max_accumulate_price": [0.61, 0.63, 0.65],
        
        # Test max_buy_price around 0.9
        "max_buy_price": [0.88, 0.90, 0.92],
        
        # Test max_ratio around 1.4
        "max_ratio": [1.2, 1.4, 1.6],
        
        # Test min_arbitrage_pair_cost around 0.92
        "min_arbitrage_pair_cost": [0.90, 0.92, 0.94],
        
        # Test max_capital_per_market around 150.0
        "max_capital_per_market": [100.0, 150.0, 200.0],
        
        # Test max_loss_threshold around 10.0
        "max_loss_threshold": [8.0, 10.0, 12.0],
    }
    
    print("🔍 Finding market data...")
    markets = find_all_data_files(args.data_dir)
    
    if not markets:
        print(f"❌ No market data found in '{args.data_dir}'")
        return
    
    print(f"📊 Found {len(markets)} markets")
    
    # Generate parameter combinations
    print(f"\n🔬 Generating parameter combinations...")
    combinations = generate_parameter_combinations(base_params, param_ranges)
    print(f"📋 Testing {len(combinations)} parameter combinations")
    
    # Run benchmarks
    results: list[BenchmarkResult] = []
    
    for i, params in enumerate(combinations, 1):
        print(f"\n[{i}/{len(combinations)}] Testing parameters...")
        print(f"  accumulate_price={params.accumulate_price}, "
              f"hedge_price={params.hedge_price}, "
              f"max_ratio={params.max_ratio}, "
              f"max_capital_per_market={params.max_capital_per_market}")
        
        result = benchmark_parameter_set(
            params=params,
            markets=markets,
            initial_balance=args.initial_balance,
            timestamp_tolerance=args.timestamp_tolerance,
            verbose=args.verbose,
        )
        
        results.append(result)
        print(f"  ✅ Profit: ${result.total_profit:.2f} ({result.total_profit_pct:.2f}%), "
              f"Trades: {result.total_trades}, Win Rate: {result.win_rate*100:.1f}%")
    
    # Print results
    print_results(results, top_n=args.top_n)
    
    # Save results
    save_results_to_json(results, args.output)


if __name__ == "__main__":
    main()

