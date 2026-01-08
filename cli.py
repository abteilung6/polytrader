"""Command-line interface for the Polymarket trading system."""

import argparse
import asyncio
import logging

from polytrader.tasks import auto_buy_task, buy_task, predict_task, watch_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket trading system")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Command to execute")

    watch_parser = subparsers.add_parser("watch", help="Watch market prices/ticks")
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

    buy_parser = subparsers.add_parser("buy", help="Place a buy order")
    buy_parser.add_argument("--market", required=True, help="Market slug")
    buy_parser.add_argument("--outcome", required=True, help="Outcome name (e.g., 'Up', 'Down')")
    buy_parser.add_argument("--amount", type=float, required=True, help="Order amount in USDC")

    predict_parser = subparsers.add_parser("predict", help="Run trading model predictions")
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
        "auto-buy", help="Automatically execute trades based on model predictions"
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

    if args.mode == "watch":
        print(f"Watching market pattern: {args.market}")
        print("Outcomes: UP, DOWN (both)")
        print(f"Frequency: {args.frequency} Hz")
        if args.limit:
            print(f"Limit: {args.limit} ticks")
        print("\nPress Ctrl+C to stop\n")
        asyncio.run(watch_task(args.market, args.frequency, args.limit))
    elif args.mode == "buy":
        response = buy_task(args.market, args.outcome, args.amount)
        if isinstance(response, dict):
            order_id = response.get("order_id") or response.get("id", "N/A")
            status = response.get("status") or response.get("state", "N/A")
        else:
            order_id = "N/A"
            status = "N/A"
        print(
            f"✅ Order placed: {args.market}/{args.outcome} ${args.amount:.2f}  "
            f"ID:{order_id}  Status:{status}"
        )
    elif args.mode == "predict":
        print(f"Predicting trades for market pattern: {args.market}")
        print("Outcomes: UP, DOWN (both)")
        print(f"Frequency: {args.frequency} Hz")
        print(f"Buy threshold: {args.buy_threshold}")
        print(f"Sell threshold: {args.sell_threshold}")
        print(f"Size: ${args.size}")
        print(f"Min history: {args.min_history} ticks")
        print("\nPress Ctrl+C to stop\n")
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
        print(f"Auto-buy mode for market pattern: {args.market}")
        print("Outcomes: UP, DOWN (both)")
        print(f"Frequency: {args.frequency} Hz")
        print(f"Buy threshold: {args.buy_threshold}")
        print(f"Sell threshold: {args.sell_threshold}")
        print(f"Size: ${args.size}")
        print(f"Min history: {args.min_history} ticks")
        print(f"Max trades per outcome: {args.max_trades}")
        print("\nPress Ctrl+C to stop\n")
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
