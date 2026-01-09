"""Scrape command handler."""

import argparse
import asyncio
import csv
import os

from datetime import datetime, timezone

from polytrader.config import PolymarketSecrets
from polytrader.events import TICKS, EventBus
from polytrader.market_discovery import MarketSlugGenerator
from polytrader.store import MemoryTickStore
from cli.utils import (
    create_observers,
    get_current_interval_id,
    get_market_timestamp,
    resolve_market_slug,
    stop_observers,
)


def _setup_csv_file(slug: str) -> tuple[object, object, str]:
    """Set up CSV file for a market."""
    market_dt = get_market_timestamp(slug)
    date_str = market_dt.strftime("%Y-%m-%d")
    time_str = market_dt.strftime("%H-%M-%S")
    
    data_dir = os.path.join("data", slug, date_str, time_str)
    os.makedirs(data_dir, exist_ok=True)
    
    path = os.path.join(data_dir, "data.csv")
    file = open(path, "w", newline="")
    writer = csv.writer(file)
    writer.writerow(["timestamp", "market_slug", "outcome", "best_bid", "best_ask", "mid", "spread"])
    return file, writer, path


async def scrape_mode(args: argparse.Namespace) -> None:
    """Scrape market prices and save to CSV files."""
    secrets = PolymarketSecrets()
    
    # Resolve initial market slug
    market_slug, auto_refresh = resolve_market_slug(args.asset, args.time_period, args.market)
    current_interval_id: str | None = None
    
    if auto_refresh:
        current_interval_id = get_current_interval_id(args.asset, args.time_period)
        print(f"Resolved market slug: {market_slug}")
        print(f"Auto-refresh enabled: will switch to new market when interval changes")
    
    # Always watch both outcomes
    outcomes_to_watch = ["Up", "Down"]
    
    bus = EventBus()
    store = MemoryTickStore()
    
    # Create initial observers
    observers, observer_tasks = await create_observers(
        market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
    )
    
    tick_queue = bus.subscribe(TICKS)
    
    # Initialize CSV file for first market
    csv_file, csv_writer, csv_path = _setup_csv_file(market_slug)
    count = 0
    total_count = 0
    consecutive_no_data = 0
    max_consecutive_no_data = 20  # Stop after 20 consecutive failures
    
    # Get market expiration time
    expiration_time = MarketSlugGenerator.get_market_expiration_time(market_slug)
    
    print(f"Scraping market: {market_slug}")
    print(f"Outcomes: {', '.join(outcomes_to_watch)}")
    print(f"Frequency: {args.frequency} Hz")
    if expiration_time:
        print(f"Market expires at: {expiration_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Saving to: {csv_path}")
    print("\nPress Ctrl+C to stop\n")
    
    try:
        check_interval_counter = 0
        
        while True:
            # Check for interval change (for auto-refresh)
            if auto_refresh and check_interval_counter >= 10:
                check_interval_counter = 0
                new_interval_id = get_current_interval_id(args.asset, args.time_period)
                
                if new_interval_id != current_interval_id:
                    # Interval has changed - switch to new market
                    print(f"\n⚠️  Interval changed! Switching to new market...")
                    print(f"   Closed {market_slug} with {count} ticks")
                    
                    # Close current CSV file
                    csv_file.close()
                    
                    # Stop old observers
                    await stop_observers(observers, observer_tasks)
                    
                    # Get new market slug
                    new_market_slug = MarketSlugGenerator.get_latest_slug(args.asset, args.time_period)
                    current_interval_id = new_interval_id
                    market_slug = new_market_slug
                    
                    # Set up new CSV file
                    csv_file, csv_writer, csv_path = _setup_csv_file(market_slug)
                    count = 0  # Reset count for new market
                    
                    # Get expiration time for new market
                    expiration_time = MarketSlugGenerator.get_market_expiration_time(market_slug)
                    
                    # Create new observers
                    observers, observer_tasks = await create_observers(
                        market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
                    )
                    
                    print(f"✅ Now scraping: {market_slug}")
                    if expiration_time:
                        print(f"   Market expires at: {expiration_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    print(f"   Saving to: {csv_path}\n")
            
            # Check if market has expired (only if not auto-refreshing, or as fallback)
            if expiration_time and not auto_refresh:
                now_utc = datetime.now(timezone.utc)
                if now_utc >= expiration_time:
                    print(f"\n⏰ Market has expired at {expiration_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    if auto_refresh:
                        # Will be handled by interval check above
                        continue
                    else:
                        print("Stopping scraper...")
                        await stop_observers(observers, observer_tasks)
                        break
            
            # Wait for tick with timeout to periodically check expiration
            try:
                tick = await asyncio.wait_for(tick_queue.get(), timeout=1.0)
                consecutive_no_data = 0  # Reset counter on successful tick
                count += 1
                total_count += 1
                check_interval_counter += 1
                
                # Write tick to CSV
                csv_writer.writerow([
                    tick.ts,
                    tick.market_id,
                    tick.outcome,
                    tick.best_bid,
                    tick.best_ask,
                    tick.mid,
                    tick.spread,
                ])
                csv_file.flush()  # Ensure data is written immediately
                
                # Print progress every 10 ticks
                if count % 10 == 0:
                    print(f"Scraped {count} ticks for {market_slug} (total: {total_count})... (saved to {csv_path})")
                
                if args.limit and total_count >= args.limit:
                    print(f"\nReached limit of {args.limit} ticks. Stopping...")
                    await stop_observers(observers, observer_tasks)
                    break
            except asyncio.TimeoutError:
                # Timeout occurred - check if market expired or if we should continue
                if expiration_time and not auto_refresh:
                    now_utc = datetime.now(timezone.utc)
                    if now_utc >= expiration_time:
                        print(f"\n⏰ Market has expired at {expiration_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        print("Stopping scraper...")
                        await stop_observers(observers, observer_tasks)
                        break
                # If no expiration time or not expired, continue waiting
                consecutive_no_data += 1
                if consecutive_no_data >= max_consecutive_no_data:
                    print(f"\n⚠️  No data received for {max_consecutive_no_data} consecutive attempts.")
                    if auto_refresh:
                        print("Will try to switch to next market on next interval check...")
                        consecutive_no_data = 0  # Reset and continue
                    else:
                        print("Market may have expired or closed. Stopping scraper...")
                        await stop_observers(observers, observer_tasks)
                        break
                continue
    
    except KeyboardInterrupt:
        print("\n\nStopped by user")
        await stop_observers(observers, observer_tasks)
    finally:
        if csv_file:
            csv_file.close()
        print(f"\n✅ Scraped {total_count} ticks total ({count} in current market)")
        if csv_path:
            print(f"Last data saved to: {csv_path}")

