"""Argument parser setup for CLI commands."""

import argparse


def create_watch_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create parser for watch command."""
    watch_parser = subparsers.add_parser("watch", help="Watch market prices/ticks")
    market_group = watch_parser.add_mutually_exclusive_group(required=True)
    market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp"],
        help="Asset name (requires --time-period)",
    )
    watch_parser.add_argument(
        "--time-period",
        choices=["15m", "1h"],
        help="Time period: 15m (15-minute) or 1h (hourly) (required with --asset)",
    )
    watch_parser.add_argument(
        "--frequency",
        type=float,
        default=1.0,
        help="Polling frequency in Hz (default: 1.0)",
    )
    watch_parser.add_argument(
        "--limit",
        type=int,
        help="Number of ticks to show (default: unlimited)",
    )
    watch_parser.add_argument(
        "--trade",
        action="store_true",
        help="Enable automated trading with portfolio manager",
    )
    watch_parser.add_argument(
        "--money",
        action="store_true",
        help="Execute real orders on Polymarket (requires --trade). WARNING: This will spend real money!",
    )
    watch_parser.add_argument(
        "--initial-balance",
        type=float,
        help="Initial USDC balance for trading (default: 1000.0)",
    )
    watch_parser.add_argument(
        "--strategy",
        default="gabagool",
        help="Trading strategy (default: gabagool). Options: gabagool (aliases: gaba, paircost, asymmetric)",
    )
    return watch_parser


def create_buy_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create parser for buy command."""
    buy_parser = subparsers.add_parser("buy", help="Place a buy order")
    buy_market_group = buy_parser.add_mutually_exclusive_group(required=True)
    buy_market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    buy_market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp"],
        help="Asset name (requires --time-period). Supported: bitcoin, btc, ethereum, eth, solana, sol",
    )
    buy_parser.add_argument(
        "--time-period",
        choices=["15m", "1h"],
        help="Time period: 15m (15-minute) or 1h (hourly) (required with --asset)",
    )
    buy_parser.add_argument("--amount", type=float, required=True, help="Order amount in USDC")
    return buy_parser


def create_scrape_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create parser for scrape command."""
    scrape_parser = subparsers.add_parser("scrape", help="Scrape market prices to CSV for backtesting")
    scrape_market_group = scrape_parser.add_mutually_exclusive_group(required=True)
    scrape_market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    scrape_market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp"],
        help="Asset name (requires --time-period)",
    )
    scrape_parser.add_argument(
        "--time-period",
        choices=["15m", "1h"],
        help="Time period: 15m (15-minute) or 1h (hourly) (required with --asset)",
    )
    scrape_parser.add_argument(
        "--frequency",
        type=float,
        default=1.0,
        help="Polling frequency in Hz (default: 1.0)",
    )
    scrape_parser.add_argument(
        "--limit",
        type=int,
        help="Number of ticks to scrape (default: unlimited)",
    )
    return scrape_parser


def create_backtest_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create parser for backtest command."""
    backtest_parser = subparsers.add_parser("backtest", help="Backtest trading strategies on historical market data")
    backtest_parser.add_argument(
        "--strategy",
        type=str,
        default="gabagool-v5",
        help="Strategy to backtest (default: gabagool-v5)",
    )
    backtest_parser.add_argument(
        "--initial-balance",
        type=float,
        default=1000.0,
        help="Initial balance in USDC (default: 1000.0)",
    )
    backtest_parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Directory containing market data (default: data)",
    )
    backtest_parser.add_argument(
        "--timestamp-tolerance",
        type=float,
        default=0.1,
        help="Maximum timestamp difference for matching UP/DOWN ticks in seconds (default: 0.1)",
    )
    backtest_parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Backtest only a specific market slug (default: all markets)",
    )
    return backtest_parser


def create_parser() -> argparse.ArgumentParser:
    """Create main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(description="Polymarket trading system")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Command to execute")
    
    create_watch_parser(subparsers)
    create_buy_parser(subparsers)
    create_scrape_parser(subparsers)
    create_backtest_parser(subparsers)
    
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate parsed arguments."""
    # Validate that time-period is provided when asset is specified
    if args.mode == "watch" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    if args.mode == "buy" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    if args.mode == "scrape" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    
    # Validate that --money requires --trade
    if args.mode == "watch" and args.money and not args.trade:
        parser.error("--money requires --trade to be enabled")

