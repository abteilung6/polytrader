import argparse
import asyncio

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.adapters.polymarket import PolymarketAdapterConfig, PolymarketMarketDataAdapter
from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.events import EventBus
from polytrader.gamma import GammaClient
from polytrader.observer import Observer


async def watch_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    config = PolymarketAdapterConfig(
        market_slug=args.market,
        outcome=args.outcome,
        polling_frequency_hz=args.frequency,
        secrets=secrets,
    )

    bus = EventBus()
    adapter = PolymarketMarketDataAdapter(config)
    observer = Observer(bus, adapter)

    tick_queue = bus.subscribe("ticks")

    print(f"Watching market: {args.market}")
    print(f"Outcome: {args.outcome}")
    print(f"Frequency: {args.frequency} Hz")
    if args.limit:
        print(f"Limit: {args.limit} ticks")
    print("\nPress Ctrl+C to stop\n")

    observer_task = asyncio.create_task(observer.run())

    try:
        count = 0
        while True:
            tick = await tick_queue.get()
            count += 1
            print(f"Tick #{count}:")
            print(f"  Timestamp: {tick.ts:.3f}")
            print(f"  Market: {tick.market_id}")
            print(f"  Outcome: {tick.outcome}")
            print(f"  Best Bid: {tick.best_bid:.4f}")
            print(f"  Best Ask: {tick.best_ask:.4f}")
            print(f"  Mid Price: {tick.mid:.4f}")
            print(f"  Spread: {tick.spread:.4f}")
            print()

            if args.limit and count >= args.limit:
                print(f"Reached limit of {args.limit} ticks. Stopping...")
                observer.stop()
                break

    except KeyboardInterrupt:
        print("\nStopped by user")
        observer.stop()
    finally:
        observer_task.cancel()
        try:
            await observer_task
        except asyncio.CancelledError:
            pass


def buy_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    print("Secrets loaded successfully!")

    gamma = GammaClient()
    market = gamma.get_market_by_slug(args.market)
    token_id = market.get_token_id(args.outcome)
    print(f"Token ID for '{args.outcome}': {token_id}")

    client = ClobClient(
        host=CLOB_API_URL,
        key=secrets.private_key.get_secret_value(),
        chain_id=CHAIN_ID,
        signature_type=secrets.signature_type,
        funder=secrets.funder,
    )

    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)

    verify_usdc_balance(client, required_amount=args.amount)

    response = place_market_order(client, token_id=token_id, amount=args.amount, side=BUY)
    print(f"Order placed! Response: {response}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket trading system")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Command to execute")

    watch_parser = subparsers.add_parser("watch", help="Watch market prices/ticks")
    watch_parser.add_argument("--market", required=True, help="Market slug")
    watch_parser.add_argument(
        "--outcome", choices=["Up", "Down"], required=True, help="Market outcome"
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

    args = parser.parse_args()

    if args.mode == "watch":
        asyncio.run(watch_mode(args))
    elif args.mode == "buy":
        buy_mode(args)


if __name__ == "__main__":
    main()
