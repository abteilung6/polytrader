import argparse
import asyncio
from datetime import datetime, timezone

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.adapters.polymarket import PolymarketAdapterConfig, PolymarketMarketDataAdapter
from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.events import TICKS, EventBus
from polytrader.gamma import GammaClient
from polytrader.market_discovery import MarketSlugGenerator
from polytrader.observer import Observer
from polytrader.store import MemoryTickStore
from polytrader.types import MarketTick, Outcome


def get_current_interval_id(asset: str, time_period: str) -> str:
    """Get current interval identifier for checking if market slug needs refresh.
    
    For 15-minute markets: returns the aligned timestamp string
    For hourly markets: returns the hour identifier string (month-day-hour-am/pm)
    """
    period = MarketSlugGenerator.normalize_time_period(time_period)
    
    if period == "15min":
        # Return the aligned timestamp
        now_utc = datetime.now(timezone.utc)
        current_timestamp = int(now_utc.timestamp())
        aligned_timestamp = current_timestamp - (current_timestamp % 900)
        return str(aligned_timestamp)
    elif period == "1h":
        # Return hour identifier
        _, long_format = MarketSlugGenerator.normalize_asset(asset)
        slug = MarketSlugGenerator.get_latest_hourly_slug(asset)
        # Extract the hour part: {asset}-up-or-down-{month}-{day}-{hour}am-et
        parts = slug.split("-")
        # Return everything after "up-or-down" as identifier
        return "-".join(parts[3:])  # month-day-hour-am-et
    else:
        raise ValueError(f"Unsupported time period: {time_period}")


async def create_observers(
    market_slug: str,
    outcomes_to_watch: list[str],
    secrets: PolymarketSecrets,
    frequency: float,
    bus: EventBus,
    store: MemoryTickStore,
) -> tuple[list[Observer], list[asyncio.Task]]:
    """Create observers for the given market slug."""
    observers = []
    observer_tasks = []
    
    for outcome_cli in outcomes_to_watch:
        outcome_type: "Outcome" = "UP" if outcome_cli == "Up" else "DOWN"
        
        config = PolymarketAdapterConfig(
            market_slug=market_slug,
            outcome=outcome_type,
            polling_frequency_hz=frequency,
            secrets=secrets,
        )
        
        adapter = PolymarketMarketDataAdapter(config)
        observer = Observer(bus, adapter, store)
        observers.append(observer)
        observer_tasks.append(asyncio.create_task(observer.run()))
    
    return observers, observer_tasks


async def stop_observers(observers: list[Observer], observer_tasks: list[asyncio.Task]) -> None:
    """Stop observers and cancel their tasks."""
    for observer in observers:
        observer.stop()
    for task in observer_tasks:
        task.cancel()
    for task in observer_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


async def watch_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    
    # Determine if we should auto-refresh (only when using asset/time-period)
    auto_refresh = args.asset and args.time_period
    current_interval_id: str | None = None
    
    # Resolve initial market slug
    if auto_refresh:
        market_slug = MarketSlugGenerator.get_latest_slug(args.asset, args.time_period)
        current_interval_id = get_current_interval_id(args.asset, args.time_period)
        print(f"Resolved market slug: {market_slug}")
        print(f"Auto-refresh enabled: will switch to new market when interval changes")
    elif args.market:
        market_slug = args.market
    else:
        raise ValueError("Either --market or both --asset and --time-period must be provided")
    
    # Always watch both outcomes
    outcomes_to_watch = ["Up", "Down"]

    bus = EventBus()
    store = MemoryTickStore()
    
    # Create initial observers
    observers, observer_tasks = await create_observers(
        market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
    )

    tick_queue = bus.subscribe(TICKS)

    print(f"Watching market: {market_slug}")
    print(f"Outcomes: {', '.join(outcomes_to_watch)}")
    print(f"Frequency: {args.frequency} Hz")
    if args.limit:
        print(f"Limit: {args.limit} ticks")
    print("\nPress Ctrl+C to stop\n")

    # Track latest ticks for each outcome
    latest_ticks: dict[str, "MarketTick"] = {}
    
    # Print table header
    if len(outcomes_to_watch) > 1:
        # Table format for multiple outcomes
        header = f"{'Outcome':<10} {'Best Bid':<12} {'Best Ask':<12} {'Mid Price':<12} {'Spread':<12} {'Timestamp':<12}"
        print(header)
        print("-" * len(header))
    else:
        # Single outcome format
        print(f"{'Tick':<6} {'Best Bid':<12} {'Best Ask':<12} {'Mid Price':<12} {'Spread':<12} {'Timestamp':<12}")
        print("-" * 70)

    try:
        count = 0
        check_interval_counter = 0  # Counter to check for interval changes periodically
        
        while True:
            tick = await tick_queue.get()
            count += 1
            check_interval_counter += 1
            
            # Check for interval change every 10 ticks (to avoid checking too frequently)
            if auto_refresh and check_interval_counter >= 10:
                check_interval_counter = 0
                new_interval_id = get_current_interval_id(args.asset, args.time_period)
                
                if new_interval_id != current_interval_id:
                    # Interval has changed - switch to new market
                    print(f"\n⚠️  Interval changed! Switching to new market...")
                    
                    # Stop old observers
                    await stop_observers(observers, observer_tasks)
                    
                    # Get new market slug
                    new_market_slug = MarketSlugGenerator.get_latest_slug(args.asset, args.time_period)
                    current_interval_id = new_interval_id
                    market_slug = new_market_slug
                    
                    # Clear old ticks
                    latest_ticks.clear()
                    
                    # Create new observers
                    observers, observer_tasks = await create_observers(
                        market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
                    )
                    
                    print(f"✅ Now watching: {market_slug}")
                    print()
            
            # Store latest tick for this outcome
            outcome_key = tick.outcome
            latest_ticks[outcome_key] = tick

            if len(outcomes_to_watch) > 1:
                # Display table with all outcomes side by side
                # Print separator and update count
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
                print(
                    f"{count:<6} {tick.best_bid:<12.4f} {tick.best_ask:<12.4f} "
                    f"{tick.mid:<12.4f} {tick.spread:<12.4f} {tick.ts:<12.3f}"
                )

            if args.limit and count >= args.limit:
                print(f"\nReached limit of {args.limit} ticks. Stopping...")
                await stop_observers(observers, observer_tasks)
                break

    except KeyboardInterrupt:
        print("\n\nStopped by user")
        await stop_observers(observers, observer_tasks)


def buy_mode(args: argparse.Namespace) -> None:
    secrets = PolymarketSecrets()
    print("Secrets loaded successfully!")

    # Resolve market slug if asset and time_period are provided
    if args.asset and args.time_period:
        market_slug = MarketSlugGenerator.get_latest_slug(args.asset, args.time_period)
        print(f"Resolved market slug: {market_slug}")
    elif args.market:
        market_slug = args.market
    else:
        raise ValueError("Either --market or both --asset and --time-period must be provided")

    gamma = GammaClient()
    market = gamma.get_market_by_slug(market_slug)
    # Default to "Up" outcome
    outcome = "Up"
    token_id = market.get_token_id(outcome)
    print(f"Token ID for '{outcome}': {token_id}")

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
    market_group = watch_parser.add_mutually_exclusive_group(required=True)
    market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth"],
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

    buy_parser = subparsers.add_parser("buy", help="Place a buy order")
    buy_market_group = buy_parser.add_mutually_exclusive_group(required=True)
    buy_market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    buy_market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth"],
        help="Asset name (requires --time-period)",
    )
    buy_parser.add_argument(
        "--time-period",
        choices=["15m", "1h"],
        help="Time period: 15m (15-minute) or 1h (hourly) (required with --asset)",
    )
    buy_parser.add_argument("--amount", type=float, required=True, help="Order amount in USDC")

    args = parser.parse_args()

    # Validate that time-period is provided when asset is specified
    if args.mode == "watch" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    if args.mode == "buy" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")

    if args.mode == "watch":
        asyncio.run(watch_mode(args))
    elif args.mode == "buy":
        buy_mode(args)


if __name__ == "__main__":
    main()
