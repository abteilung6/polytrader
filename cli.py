import argparse
import asyncio
import csv
import os
from datetime import datetime, timezone

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]
from py_clob_client.order_builder.constants import BUY  # type: ignore[import-untyped]

from polytrader.adapters.polymarket import PolymarketAdapterConfig, PolymarketMarketDataAdapter
from polytrader.clob import place_market_order, verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.core import PortfolioManager
from polytrader.core.position import Position
from polytrader.core.strategy_registry import create_strategy
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
        # Return the current 15-minute interval (round down)
        # This gets the currently active market
        now_utc = datetime.now(timezone.utc)
        current_timestamp = int(now_utc.timestamp())
        aligned_timestamp = (current_timestamp // 900) * 900
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
    
    # Initialize portfolio manager if trading is enabled
    portfolio_manager: PortfolioManager | None = None
    if args.trade:
        strategy = create_strategy(args.strategy)
        portfolio_manager = PortfolioManager(
            initial_balance=args.initial_balance or 1000.0,
            strategy=strategy,
        )
        print(f"💰 Trading enabled:")
        print(f"   Initial balance: ${portfolio_manager.get_balance():.2f} USDC")
        print(f"   Strategy: {strategy}")
        print()
    
    # Create initial observers
    observers, observer_tasks = await create_observers(
        market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
    )

    tick_queue = bus.subscribe(TICKS)
    
    # Track expiration time for initial market if trading is enabled
    market_expirations: dict[str, datetime] = {}
    if portfolio_manager:
        expiration_time = MarketSlugGenerator.get_market_expiration_time(market_slug)
        if expiration_time:
            market_expirations[market_slug] = expiration_time

    print(f"Watching market: {market_slug}")
    print(f"Outcomes: {', '.join(outcomes_to_watch)}")
    print(f"Frequency: {args.frequency} Hz")
    if args.limit:
        print(f"Limit: {args.limit} ticks")
    print("\nPress Ctrl+C to stop\n")

    # Track latest ticks for each outcome
    latest_ticks: dict[str, "MarketTick"] = {}
    # Track latest prices per market (for calculating portfolio value)
    market_prices: dict[tuple[str, Outcome], float] = {}
    # Track when we last successfully received a tick for each outcome (to detect API errors)
    last_successful_tick_time: dict[str, float] = {}
    
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
            
            # Check for expired markets and settle positions
            if portfolio_manager and check_interval_counter >= 10:
                now_utc = datetime.now(timezone.utc)
                expired_markets: list[str] = []
                
                for market_id, expiration_time in market_expirations.items():
                    if now_utc >= expiration_time:
                        expired_markets.append(market_id)
                
                # Settle expired markets
                for expired_market_id in expired_markets:
                    # Get latest prices for this market
                    up_tick = latest_ticks.get("UP")
                    down_tick = latest_ticks.get("DOWN")
                    
                    if up_tick and down_tick and up_tick.market_id == expired_market_id:
                        # Determine winner based on highest price
                        settlement_info = portfolio_manager.expire_positions(
                            market_id=expired_market_id,
                            up_price=up_tick.mid,
                            down_price=down_tick.mid,
                        )
                        
                        winner = settlement_info["winner"]
                        positions_settled = settlement_info["positions_settled"]
                        total_payout = settlement_info["total_payout"]
                        
                        print(f"\n⏰ Market expired: {expired_market_id}")
                        print(f"   Winner: {winner} (UP: ${up_tick.mid:.4f}, DOWN: ${down_tick.mid:.4f})")
                        print(f"   Positions settled: {positions_settled}")
                        print(f"   Total payout: ${total_payout:.2f} USDC")
                        print(f"   New balance: ${portfolio_manager.get_balance():.2f} USDC")
                        print()
                    
                    # Remove from tracking
                    del market_expirations[expired_market_id]
            
            # Check for interval change every 10 ticks (to avoid checking too frequently)
            if auto_refresh and check_interval_counter >= 10:
                check_interval_counter = 0
                new_interval_id = get_current_interval_id(args.asset, args.time_period)
                
                if new_interval_id != current_interval_id:
                    # Interval has changed - switch to new market
                    print(f"\n⚠️  Interval changed! Switching to new market...")
                    
                    # Before switching, check if old market expired and settle positions
                    if portfolio_manager:
                        old_expiration = MarketSlugGenerator.get_market_expiration_time(market_slug)
                        if old_expiration:
                            now_utc = datetime.now(timezone.utc)
                            if now_utc >= old_expiration:
                                up_tick = latest_ticks.get("UP")
                                down_tick = latest_ticks.get("DOWN")
                                if up_tick and down_tick:
                                    settlement_info = portfolio_manager.expire_positions(
                                        market_id=market_slug,
                                        up_price=up_tick.mid,
                                        down_price=down_tick.mid,
                                    )
                                    winner = settlement_info["winner"]
                                    total_payout = settlement_info["total_payout"]
                                    print(f"   Settled expired market: {market_slug}")
                                    print(f"   Winner: {winner}, Payout: ${total_payout:.2f} USDC")
                    
                    # Stop old observers
                    await stop_observers(observers, observer_tasks)
                    
                    # Get new market slug
                    new_market_slug = MarketSlugGenerator.get_latest_slug(args.asset, args.time_period)
                    current_interval_id = new_interval_id
                    market_slug = new_market_slug
                    
                    # Track expiration for new market
                    if portfolio_manager:
                        expiration_time = MarketSlugGenerator.get_market_expiration_time(market_slug)
                        if expiration_time:
                            market_expirations[market_slug] = expiration_time
                    
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
            # Store price for this market/outcome
            market_prices[(tick.market_id, tick.outcome)] = tick.mid
            # Mark that we successfully received a tick for this outcome
            last_successful_tick_time[outcome_key] = tick.ts

            # Process with portfolio manager if we have both UP and DOWN prices
            trade_executed = False
            if portfolio_manager and len(outcomes_to_watch) > 1:
                up_tick = latest_ticks.get("UP")
                down_tick = latest_ticks.get("DOWN")
                
                # Only trade if we have both ticks AND they are recent (within 5 seconds)
                # This ensures we don't trade on stale data if there's an API error
                current_time = tick.ts
                max_tick_age = 5.0  # Maximum age in seconds for valid ticks
                
                # Check if we have both ticks and they're both recent
                has_fresh_up = up_tick is not None and (current_time - last_successful_tick_time.get("UP", 0)) <= max_tick_age
                has_fresh_down = down_tick is not None and (current_time - last_successful_tick_time.get("DOWN", 0)) <= max_tick_age
                
                # Check if timestamps match (within small tolerance for floating point precision)
                timestamps_match = False
                if has_fresh_up and has_fresh_down:
                    timestamp_diff = abs(up_tick.ts - down_tick.ts)
                    timestamp_tolerance = 0.1  # 100ms tolerance for floating point precision
                    timestamps_match = timestamp_diff <= timestamp_tolerance
                
                if has_fresh_up and has_fresh_down and timestamps_match:
                    # Both ticks are fresh and have matching timestamps - safe to trade
                    # Use best_ask (best_bid + spread) for buying - accounts for spread
                    decision = portfolio_manager.process_prices(
                        market_id=tick.market_id,
                        up_price=up_tick.best_ask,
                        down_price=down_tick.best_ask,
                    )
                    if decision:
                        trade_executed = True
                        # Track expiration time for this market if not already tracked
                        if tick.market_id not in market_expirations:
                            expiration_time = MarketSlugGenerator.get_market_expiration_time(tick.market_id)
                            if expiration_time:
                                market_expirations[tick.market_id] = expiration_time
                else:
                    # Skip trading if we don't have fresh data for both outcomes or timestamps don't match
                    # This happens when there's an API error, stale data, or timestamps are out of sync
                    if count % 10 == 0:  # Only log occasionally to avoid spam
                        missing_or_stale = []
                        if not has_fresh_up:
                            if up_tick is None:
                                missing_or_stale.append("UP (missing)")
                            else:
                                age = current_time - last_successful_tick_time.get("UP", 0)
                                missing_or_stale.append(f"UP ({age:.1f}s old)")
                        if not has_fresh_down:
                            if down_tick is None:
                                missing_or_stale.append("DOWN (missing)")
                            else:
                                age = current_time - last_successful_tick_time.get("DOWN", 0)
                                missing_or_stale.append(f"DOWN ({age:.1f}s old)")
                        if has_fresh_up and has_fresh_down and not timestamps_match:
                            timestamp_diff = abs(up_tick.ts - down_tick.ts)
                            missing_or_stale.append(f"timestamps don't match (diff: {timestamp_diff:.3f}s)")
                        if missing_or_stale:
                            print(f"⚠️  Skipping trade: API error or stale data ({', '.join(missing_or_stale)})")

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
                
                # Show portfolio info if trading is enabled
                if portfolio_manager:
                    stats = portfolio_manager.get_statistics()
                    portfolio = portfolio_manager.get_portfolio()
                    
                    # Build price dictionary for all positions
                    # Use current market prices if available, otherwise use entry price
                    current_prices: dict[tuple[str, Outcome], float] = {}
                    for (market_id, outcome), position in portfolio.positions.items():
                        price_key = (market_id, outcome)
                        if price_key in market_prices:
                            # Use current market price
                            current_prices[price_key] = market_prices[price_key]
                        else:
                            # Use entry price as fallback
                            current_prices[price_key] = position.avg_price
                    
                    # Calculate total portfolio value (cash + current value of positions)
                    total_portfolio_value = portfolio.get_total_value(current_prices)
                    initial_balance = args.initial_balance or 1000.0
                    total_profit = total_portfolio_value - initial_balance
                    
                    # Get current market prices for display
                    up_tick = latest_ticks.get("UP")
                    down_tick = latest_ticks.get("DOWN")
                    
                    # Calculate profit scenarios for this market
                    # Get all positions for this market
                    market_positions = {
                        outcome: pos
                        for (m_id, outcome), pos in portfolio.positions.items()
                        if m_id == tick.market_id
                    }
                    
                    if market_positions:
                        # Calculate total cost for all positions in this market
                        total_cost = sum(
                            pos.quantity * pos.avg_price
                            for pos in market_positions.values()
                        )
                        
                        # Calculate profit if UP wins
                        up_position = market_positions.get("UP")
                        down_position = market_positions.get("DOWN")
                        up_value_if_up_wins = (up_position.quantity * 1.0) if up_position else 0.0
                        down_value_if_up_wins = (down_position.quantity * 0.0) if down_position else 0.0
                        profit_if_up = (up_value_if_up_wins + down_value_if_up_wins) - total_cost
                        
                        # Calculate profit if DOWN wins
                        up_value_if_down_wins = (up_position.quantity * 0.0) if up_position else 0.0
                        down_value_if_down_wins = (down_position.quantity * 1.0) if down_position else 0.0
                        profit_if_down = (up_value_if_down_wins + down_value_if_down_wins) - total_cost
                        
                        print(f"\n💼 Portfolio: Cash=${stats['balance']:.2f} | Total Value=${total_portfolio_value:.2f} | Profit=${total_profit:+.2f} | Trades={stats['total_trades']} | Positions={stats['num_positions']}")
                        print(f"   Profit if UP: ${profit_if_up:+.2f}")
                        print(f"   Profit if DOWN: ${profit_if_down:+.2f}")
                        
                        # Show positions for current market
                        if up_tick and down_tick:
                            print(f"\n   Positions in {tick.market_id}:")
                            for outcome, position in market_positions.items():
                                current_price = current_prices.get((tick.market_id, outcome), position.avg_price)
                                print(
                                    f"     {outcome}: {position.quantity:.4f} @ ${position.avg_price:.4f} "
                                    f"(Current: ${current_price:.4f})"
                                )
                    
                    if trade_executed:
                        if isinstance(decision, list):
                            # Multiple trades executed (e.g., arbitrage strategy buying both sides)
                            outcomes = ", ".join(d.outcome for d in decision)
                            total_cost = sum(d.amount for d in decision)
                            print(f"✅ Trades executed on {tick.market_id}: {outcomes} (total: ${total_cost:.2f})")
                        else:
                            print(f"✅ Trade executed on {tick.market_id}: {decision.outcome}")
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
    finally:
        # Print final portfolio statistics if trading was enabled
        if portfolio_manager:
            stats = portfolio_manager.get_statistics()
            portfolio = portfolio_manager.get_portfolio()
            
            # Build final prices using market_prices (current prices) or entry prices as fallback
            final_prices: dict[tuple[str, Outcome], float] = {}
            for (market_id, outcome), position in portfolio.positions.items():
                price_key = (market_id, outcome)
                if price_key in market_prices:
                    final_prices[price_key] = market_prices[price_key]
                else:
                    final_prices[price_key] = position.avg_price
            
            # Calculate total portfolio value
            total_portfolio_value = portfolio.get_total_value(final_prices)
            initial_balance = args.initial_balance or 1000.0
            total_profit = total_portfolio_value - initial_balance
            
            print("\n" + "=" * 80)
            print("📊 Final Portfolio Statistics:")
            print("=" * 80)
            print(f"Cash Balance: ${stats['balance']:.2f} USDC")
            print(f"Total Portfolio Value: ${total_portfolio_value:.2f} USDC")
            print(f"Total Profit: ${total_profit:+.2f} USDC ({total_profit/initial_balance*100:+.2f}%)")
            print(f"Total Trades: {stats['total_trades']}")
            print(f"Total Spent: ${stats['total_spent']:.2f} USDC")
            print(f"Open Positions: {stats['num_positions']}")
            
            if stats['num_positions'] > 0:
                # Group positions by market
                markets: dict[str, dict[Outcome, Position]] = {}
                for (market_id, outcome), position in portfolio.positions.items():
                    if market_id not in markets:
                        markets[market_id] = {}
                    markets[market_id][outcome] = position
                
                print("\nPositions:")
                print(f"{'Market':<30} {'Direction':<10} {'Quantity':<12} {'Entry Price':<12} {'Current Price':<14}")
                print("-" * 78)
                
                for market_id, market_positions in markets.items():
                    for outcome, position in market_positions.items():
                        current_price = final_prices.get((market_id, outcome), position.avg_price)
                        print(
                            f"{market_id:<30} {outcome:<10} {position.quantity:<12.4f} "
                            f"${position.avg_price:<11.4f} ${current_price:<13.4f}"
                        )
                
                print("-" * 78)
                print("\nProfit by Market:")
                print(f"{'Market':<30} {'Profit if UP':<15} {'Profit if DOWN':<15}")
                print("-" * 60)
                
                total_profit_if_all_up = 0.0
                total_profit_if_all_down = 0.0
                
                for market_id, market_positions in markets.items():
                    # Calculate total cost for all positions in this market
                    total_cost = sum(
                        pos.quantity * pos.avg_price
                        for pos in market_positions.values()
                    )
                    
                    # Calculate profit if UP wins
                    up_position = market_positions.get("UP")
                    down_position = market_positions.get("DOWN")
                    up_value_if_up_wins = (up_position.quantity * 1.0) if up_position else 0.0
                    down_value_if_up_wins = (down_position.quantity * 0.0) if down_position else 0.0
                    profit_if_up = (up_value_if_up_wins + down_value_if_up_wins) - total_cost
                    
                    # Calculate profit if DOWN wins
                    up_value_if_down_wins = (up_position.quantity * 0.0) if up_position else 0.0
                    down_value_if_down_wins = (down_position.quantity * 1.0) if down_position else 0.0
                    profit_if_down = (up_value_if_down_wins + down_value_if_down_wins) - total_cost
                    
                    total_profit_if_all_up += profit_if_up
                    total_profit_if_all_down += profit_if_down
                    
                    print(f"{market_id:<30} ${profit_if_up:+14.2f} ${profit_if_down:+14.2f}")
                
                print("-" * 60)
                print(f"{'Total':<30} ${total_profit_if_all_up:+14.2f} ${total_profit_if_all_down:+14.2f}")
                
                # Calculate total portfolio value scenarios
                total_value_if_all_up = stats['balance'] + total_profit_if_all_up
                total_value_if_all_down = stats['balance'] + total_profit_if_all_down
                
                print(f"\nTotal Portfolio Value:")
                print(f"  If all UP outcomes win: ${total_value_if_all_up:.2f}")
                print(f"  If all DOWN outcomes win: ${total_value_if_all_down:.2f}")
            
            print("=" * 80)


def get_market_timestamp(market_slug: str) -> datetime:
    """Extract timestamp from market slug and return as datetime.
    
    For 15-minute markets: extracts timestamp from slug (e.g., btc-updown-15m-1767712500)
    For hourly markets: parses date/time from slug format (e.g., bitcoin-up-or-down-january-6-9am-et)
    """
    # Check if it's a 15-minute market: {asset}-updown-15m-{timestamp}
    if "-updown-15m-" in market_slug:
        try:
            timestamp_str = market_slug.split("-updown-15m-")[-1]
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, IndexError):
            raise ValueError(f"Could not parse timestamp from market slug: {market_slug}")
    
    # Check if it's an hourly market: {asset}-up-or-down-{month}-{day}-{hour}am-et
    if "-up-or-down-" in market_slug and "-et" in market_slug:
        try:
            # Parse the date part: e.g., "january-6-9am"
            date_part = market_slug.split("-up-or-down-")[-1].replace("-et", "")
            parts = date_part.split("-")
            
            if len(parts) < 3:
                raise ValueError(f"Could not parse date from market slug: {market_slug}")
            
            month_name = parts[0]
            day = int(parts[1])
            hour_str = parts[2]
            
            # Parse hour (e.g., "9am" or "2pm")
            if hour_str.endswith("am"):
                hour = int(hour_str[:-2])
                if hour == 12:
                    hour = 0
            elif hour_str.endswith("pm"):
                hour = int(hour_str[:-2])
                if hour != 12:
                    hour += 12
            else:
                raise ValueError(f"Could not parse hour from market slug: {market_slug}")
            
            # Get current year (markets are typically for current year)
            now_utc = datetime.now(timezone.utc)
            year = now_utc.year
            
            # Convert month name to number
            month_map = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12
            }
            month = month_map.get(month_name.lower())
            if month is None:
                raise ValueError(f"Unknown month name: {month_name}")
            
            # Create datetime in ET timezone
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                try:
                    from backports.zoneinfo import ZoneInfo  # type: ignore
                except ImportError:
                    ZoneInfo = None  # type: ignore
            
            if ZoneInfo is not None:
                et_tz = ZoneInfo("America/New_York")
                market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz)
            else:
                from datetime import timedelta
                et_offset = timedelta(hours=-5)
                et_tz_fallback = timezone(et_offset, name="ET")
                market_start_et = datetime(year, month, day, hour, 0, 0, tzinfo=et_tz_fallback)
            
            # Convert to UTC
            return market_start_et.astimezone(timezone.utc)
        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Could not parse date/time from market slug: {market_slug}") from e
    
    raise ValueError(f"Unknown market slug format: {market_slug}")


async def scrape_mode(args: argparse.Namespace) -> None:
    """Scrape market prices and save to CSV files."""
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
    
    # Initialize CSV file for first market
    csv_file = None
    csv_writer = None
    csv_path = None
    count = 0
    total_count = 0
    consecutive_no_data = 0
    max_consecutive_no_data = 20  # Stop after 20 consecutive failures
    
    def setup_csv_file(slug: str) -> tuple[object, object, str]:
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
    
    # Set up initial CSV file
    csv_file, csv_writer, csv_path = setup_csv_file(market_slug)
    
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
                    csv_file, csv_writer, csv_path = setup_csv_file(market_slug)
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
    watch_parser.add_argument(
        "--trade",
        action="store_true",
        help="Enable automated trading with portfolio manager",
    )
    watch_parser.add_argument(
        "--initial-balance",
        type=float,
        help="Initial USDC balance for trading (default: 1000.0)",
    )
    watch_parser.add_argument(
        "--strategy",
        default="random",
        help="Trading strategy (default: random) - 'random' or 'balancedpair' (aliases: balanced, lockprofit, gabagool)",
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

    scrape_parser = subparsers.add_parser("scrape", help="Scrape market prices to CSV for backtesting")
    scrape_market_group = scrape_parser.add_mutually_exclusive_group(required=True)
    scrape_market_group.add_argument("--market", help="Market slug (e.g., btc-updown-15m-1767709800)")
    scrape_market_group.add_argument(
        "--asset",
        choices=["bitcoin", "btc", "ethereum", "eth"],
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

    args = parser.parse_args()

    # Validate that time-period is provided when asset is specified
    if args.mode == "watch" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    if args.mode == "buy" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")
    if args.mode == "scrape" and args.asset and not args.time_period:
        parser.error("--time-period is required when --asset is specified")

    if args.mode == "watch":
        asyncio.run(watch_mode(args))
    elif args.mode == "buy":
        buy_mode(args)
    elif args.mode == "scrape":
        asyncio.run(scrape_mode(args))


if __name__ == "__main__":
    main()
