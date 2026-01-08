"""Command-line interface for the Polymarket trading system."""

import argparse
import asyncio

from polytrader.logging_config import logger, setup_logging
from polytrader.tasks import auto_buy_task, buy_task, predict_task, watch_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket trading system")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Command to execute")

    # Common argument for all subcommands
    log_file_parser = argparse.ArgumentParser(add_help=False)
    log_file_parser.add_argument(
        "--log-file",
        type=str,
        help="Optional file path to save logs (default: logs only to console)",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Watch market prices/ticks", parents=[log_file_parser]
    )
    watch_parser.add_argument(
        "--market",
        required=True,
        help="Market pattern (e.g., 'btc-updown-15m') or market slug",
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

    buy_parser = subparsers.add_parser("buy", help="Place a buy order", parents=[log_file_parser])
    buy_parser.add_argument("--market", required=True, help="Market slug")
    buy_parser.add_argument("--outcome", required=True, help="Outcome name (e.g., 'Up', 'Down')")
    buy_parser.add_argument("--amount", type=float, required=True, help="Order amount in USDC")

    predict_parser = subparsers.add_parser(
        "predict", help="Run trading model predictions", parents=[log_file_parser]
    )
    predict_parser.add_argument(
        "--market",
        required=True,
        help="Market pattern (e.g., 'btc-updown-15m') or market slug",
    )
    predict_parser.add_argument(
        "--frequency",
        type=float,
        default=1.0,
        help="Polling frequency in Hz (default: 1.0)",
    )
    predict_parser.add_argument(
        "--buy-threshold",
        type=float,
        default=0.30,
        help="Buy threshold price (default: 0.30)",
    )
    predict_parser.add_argument(
        "--sell-threshold",
        type=float,
        default=0.50,
        help="Sell threshold price (default: 0.50)",
    )
    predict_parser.add_argument(
        "--size",
        type=float,
        default=1.0,
        help="Trade size in USD (default: 1.0)",
    )
    predict_parser.add_argument(
        "--min-history",
        type=int,
        default=30,
        help="Minimum history ticks required (default: 30)",
    )

    auto_buy_parser = subparsers.add_parser(
        "auto-buy",
        help="Automatically execute trades based on model predictions",
        parents=[log_file_parser],
    )
    auto_buy_parser.add_argument(
        "--market",
        required=True,
        help="Market pattern (e.g., 'btc-updown-15m') or market slug",
    )
    auto_buy_parser.add_argument(
        "--frequency",
        type=float,
        default=1.0,
        help="Polling frequency in Hz (default: 1.0)",
    )
    auto_buy_parser.add_argument(
        "--buy-threshold",
        type=float,
        default=0.30,
        help="Buy threshold price (default: 0.30)",
    )
    auto_buy_parser.add_argument(
        "--sell-threshold",
        type=float,
        default=0.50,
        help="Sell threshold price (default: 0.50)",
    )
    auto_buy_parser.add_argument(
        "--size",
        type=float,
        default=1.0,
        help="Trade size in USD (default: 1.0)",
    )
    auto_buy_parser.add_argument(
        "--min-history",
        type=int,
        default=30,
        help="Minimum history ticks required (default: 30)",
    )
    auto_buy_parser.add_argument(
        "--max-trades",
        type=int,
        default=1,
        help="Maximum trades per market (default: 1)",
    )

    args = parser.parse_args()

    # Setup logging with optional file output
    log_file = None
    if args.log_file:
        from pathlib import Path

        log_file = Path(args.log_file)
    setup_logging(level="INFO", log_file=log_file)

    if log_file:
        logger.info("Logging to file: {file}", file=log_file)

    if args.mode == "watch":
        logger.info("Watching market pattern: {market}", market=args.market)
        logger.info("Outcomes: UP, DOWN (both)")
        logger.info("Frequency: {frequency} Hz", frequency=args.frequency)
        if args.limit:
            logger.info("Limit: {limit} ticks", limit=args.limit)
        logger.info("Press Ctrl+C to stop")
        asyncio.run(watch_task(args.market, args.frequency, args.limit))
    elif args.mode == "buy":
        response = buy_task(args.market, args.outcome, args.amount)
        if isinstance(response, dict):
            order_id = response.get("order_id") or response.get("id", "N/A")
            status = response.get("status") or response.get("state", "N/A")
        else:
            order_id = "N/A"
            status = "N/A"
        logger.info(
            "✅ Order placed: {market}/{outcome} ${amount:.2f}  ID:{order_id}  Status:{status}",
            market=args.market,
            outcome=args.outcome,
            amount=args.amount,
            order_id=order_id,
            status=status,
        )
    elif args.mode == "predict":
        logger.info("Predicting trades for market pattern: {market}", market=args.market)
        logger.info("Outcomes: UP, DOWN (both)")
        logger.info("Frequency: {frequency} Hz", frequency=args.frequency)
        logger.info("Buy threshold: {threshold}", threshold=args.buy_threshold)
        logger.info("Sell threshold: {threshold}", threshold=args.sell_threshold)
        logger.info("Size: ${size}", size=args.size)
        logger.info("Min history: {min_history} ticks", min_history=args.min_history)
        logger.info("Press Ctrl+C to stop")
        asyncio.run(
            predict_task(
                args.market,
                args.frequency,
                args.buy_threshold,
                args.sell_threshold,
                args.size,
                args.min_history,
            )
        )
    elif args.mode == "auto-buy":
        logger.info("Auto-buy mode for market pattern: {market}", market=args.market)
        logger.info("Outcomes: UP, DOWN (both)")
        logger.info("Frequency: {frequency} Hz", frequency=args.frequency)
        logger.info("Buy threshold: {threshold}", threshold=args.buy_threshold)
        logger.info("Sell threshold: {threshold}", threshold=args.sell_threshold)
        logger.info("Size: ${size}", size=args.size)
        logger.info("Min history: {min_history} ticks", min_history=args.min_history)
        logger.info("Max trades per outcome: {max_trades}", max_trades=args.max_trades)
        logger.info("Press Ctrl+C to stop")
        asyncio.run(
            auto_buy_task(
                args.market,
                args.frequency,
                args.buy_threshold,
                args.sell_threshold,
                args.size,
                args.min_history,
                args.max_trades,
            )
        )


if __name__ == "__main__":
    main()
