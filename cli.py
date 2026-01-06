import argparse
import asyncio
import logging
from datetime import datetime

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.adapters.polymarket import PolymarketAdapterConfig, PolymarketMarketDataAdapter
from polytrader.clob import create_clob_client_factory, place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.events import ORDERS, PROPOSALS, TICKS, EventBus
from polytrader.gamma import GammaClient
from polytrader.models import SimpleThresholdModel
from polytrader.observer import Observer
from polytrader.order_manager import OrderManager
from polytrader.store import MemoryTickStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def watch_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    config = PolymarketAdapterConfig(
        market_slug=args.market,
        outcome=args.outcome,
        polling_frequency_hz=args.frequency,
        secrets=secrets,
    )

    bus = EventBus()
    store = MemoryTickStore()
    adapter = PolymarketMarketDataAdapter(config)
    observer = Observer(bus, adapter, store)

    tick_queue = bus.subscribe(TICKS)

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


async def predict_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    config = PolymarketAdapterConfig(
        market_slug=args.market,
        outcome=args.outcome.upper(),
        polling_frequency_hz=args.frequency,
        secrets=secrets,
    )

    bus = EventBus()
    store = MemoryTickStore()
    adapter = PolymarketMarketDataAdapter(config)
    observer = Observer(bus, adapter, store)

    model = SimpleThresholdModel(
        bus=bus,
        store=store,
        market_id=args.market,
        outcome=args.outcome.upper(),
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        size=args.size,
        min_history=args.min_history,
    )

    proposal_queue = bus.subscribe(PROPOSALS)

    print(f"Predicting trades for market: {args.market}")
    print(f"Outcome: {args.outcome}")
    print(f"Frequency: {args.frequency} Hz")
    print(f"Buy threshold: {args.buy_threshold}")
    print(f"Sell threshold: {args.sell_threshold}")
    print(f"Size: ${args.size}")
    print(f"Min history: {args.min_history} ticks")
    print("\nPress Ctrl+C to stop\n")

    observer_task = asyncio.create_task(observer.run())
    model_task = asyncio.create_task(model.run())

    try:
        while True:
            proposal = await proposal_queue.get()
            print("Trade Proposal:")
            print(f"  Timestamp: {proposal.ts:.3f}")
            print(f"  Market: {proposal.market_id}")
            print(f"  Outcome: {proposal.outcome}")
            print(f"  Side: {proposal.side}")
            print(f"  Target Price: {proposal.target_price:.4f}")
            print(f"  Limit Price: {proposal.limit_price:.4f}")
            print(f"  Size: ${proposal.size}")
            print(f"  Reason: {proposal.reason}")
            print()

    except KeyboardInterrupt:
        print("\nStopped by user")
        observer.stop()
        model.stop()
    finally:
        observer_task.cancel()
        model_task.cancel()
        try:
            await observer_task
            await model_task
        except asyncio.CancelledError:
            pass


async def auto_buy_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    config = PolymarketAdapterConfig(
        market_slug=args.market,
        outcome=args.outcome.upper(),
        polling_frequency_hz=args.frequency,
        secrets=secrets,
    )

    bus = EventBus()
    store = MemoryTickStore()
    adapter = PolymarketMarketDataAdapter(config)
    observer = Observer(bus, adapter, store)

    model = SimpleThresholdModel(
        bus=bus,
        store=store,
        market_id=args.market,
        outcome=args.outcome.upper(),
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        size=args.size,
        min_history=args.min_history,
    )

    clob_client_factory = create_clob_client_factory(secrets)
    order_manager = OrderManager(
        bus=bus,
        clob_client_factory=clob_client_factory,
        max_trades_per_market=args.max_trades,
    )

    order_queue = bus.subscribe(ORDERS)

    print(f"Auto-buy mode for market: {args.market}")
    print(f"Outcome: {args.outcome}")
    print(f"Frequency: {args.frequency} Hz")
    print(f"Buy threshold: {args.buy_threshold}")
    print(f"Sell threshold: {args.sell_threshold}")
    print(f"Size: ${args.size}")
    print(f"Min history: {args.min_history} ticks")
    print(f"Max trades per market: {args.max_trades}")
    print("\nPress Ctrl+C to stop\n")

    observer_task = asyncio.create_task(observer.run())
    model_task = asyncio.create_task(model.run())
    order_manager_task = asyncio.create_task(order_manager.run())

    try:
        while True:
            order = await order_queue.get()
            order_time = datetime.fromtimestamp(order.ts).strftime("%Y-%m-%d %H:%M:%S")

            print("\n" + "=" * 60)
            print("✅ ORDER EXECUTED SUCCESSFULLY")
            print("=" * 60)
            print(f"Time:        {order_time}")
            print(f"Market:      {order.market_id}")
            print(f"Outcome:     {order.outcome}")
            print(f"Side:        {order.side}")
            print(f"Size:        ${order.size:.2f} USDC")
            print(f"Reason:      {order.proposal_reason}")

            response = order.response
            if isinstance(response, dict):
                order_id = response.get("order_id") or response.get("id") or "N/A"
                status = response.get("status") or response.get("state") or "N/A"
                fills = response.get("fills", [])

                print("\nOrder Details:")
                print(f"  Order ID:   {order_id}")
                print(f"  Status:     {status}")

                if fills:
                    print(f"  Fills:      {len(fills)} fill(s)")
                    for i, fill in enumerate(fills, 1):
                        price = fill.get("price", "N/A")
                        size = fill.get("size", "N/A")
                        print(f"    Fill {i}: {size} @ {price}")
                else:
                    print("  Fills:      No fills yet")

                if "error" in response:
                    print(f"  ⚠️  Error:   {response['error']}")

                print("\nFull Response:")
                for key, value in response.items():
                    if key not in ["order_id", "id", "status", "state", "fills"]:
                        print(f"  {key}: {value}")
            else:
                print(f"\nResponse: {response}")

            print("=" * 60 + "\n")

    except KeyboardInterrupt:
        print("\nStopped by user")
        observer.stop()
        model.stop()
        order_manager.stop()
    finally:
        observer_task.cancel()
        model_task.cancel()
        order_manager_task.cancel()
        try:
            await observer_task
            await model_task
            await order_manager_task
        except asyncio.CancelledError:
            pass


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

    predict_parser = subparsers.add_parser("predict", help="Run trading model predictions")
    predict_parser.add_argument("--market", required=True, help="Market slug")
    predict_parser.add_argument(
        "--outcome", choices=["Up", "Down"], required=True, help="Market outcome"
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
    auto_buy_parser.add_argument("--market", required=True, help="Market slug")
    auto_buy_parser.add_argument(
        "--outcome", choices=["Up", "Down"], required=True, help="Market outcome"
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
        asyncio.run(watch_mode(args))
    elif args.mode == "buy":
        buy_mode(args)
    elif args.mode == "predict":
        asyncio.run(predict_mode(args))
    elif args.mode == "auto-buy":
        asyncio.run(auto_buy_mode(args))


if __name__ == "__main__":
    main()
