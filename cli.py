"""Main CLI entry point for polytrader."""

import asyncio

from cli.commands.backtest import backtest_mode
from cli.commands.buy import buy_mode
from cli.commands.scrape import scrape_mode
from cli.commands.watch import watch_mode
from cli.parsers import create_parser, validate_args


def main() -> None:
    """Main entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args()
    validate_args(parser, args)
    
    if args.mode == "watch":
        asyncio.run(watch_mode(args))
    elif args.mode == "buy":
        buy_mode(args)
    elif args.mode == "scrape":
        asyncio.run(scrape_mode(args))
    elif args.mode == "backtest":
        backtest_mode(args)


if __name__ == "__main__":
    main()
