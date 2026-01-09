"""Watch command handler."""

import argparse
import asyncio
from datetime import datetime, timezone

from py_clob_client.client import ClobClient  # type: ignore[import-untyped]

from polytrader.clob import verify_usdc_balance
from polytrader.config import CHAIN_ID, CLOB_API_URL, PolymarketSecrets
from polytrader.core import PortfolioManager
from polytrader.events import TICKS, EventBus
from polytrader.gamma import GammaClient
from polytrader.market_discovery import MarketSlugGenerator
from polytrader.store import MemoryTickStore
from polytrader.types import MarketTick, Outcome
from cli.utils import (
    create_observers,
    get_current_interval_id,
    resolve_market_slug,
    stop_observers,
)
from cli.formatters import (
    print_final_portfolio_stats,
    print_market_expired,
    print_portfolio_info,
    print_tick_table,
    print_trade_executed,
    print_watch_header,
)
from polytrader.core.strategies import create_strategy


def _setup_portfolio_manager(
    args: argparse.Namespace,
    secrets: PolymarketSecrets,
) -> tuple[PortfolioManager | None, ClobClient | None, GammaClient | None]:
    """Set up portfolio manager and clients if trading is enabled."""
    if not args.trade:
        return None, None, None
    
    clob_client: ClobClient | None = None
    gamma_client: GammaClient | None = None
    
    if args.money:
        # Validate that we have secrets for real trading
        if not secrets.private_key:
            raise ValueError("--money requires private key to be configured in secrets")
        
        # Initialize ClobClient for real order execution
        clob_client = ClobClient(
            host=CLOB_API_URL,
            key=secrets.private_key.get_secret_value(),
            chain_id=CHAIN_ID,
            signature_type=secrets.signature_type,
            funder=secrets.funder,
        )
        
        try:
            creds = clob_client.create_or_derive_api_creds()
            clob_client.set_api_creds(creds)
        except Exception as e:
            print(f"⚠️  Warning: Could not set API credentials: {e}")
        
        # Initialize GammaClient for getting token IDs
        gamma_client = GammaClient()
        
        # Verify balance
        try:
            balance = verify_usdc_balance(clob_client, required_amount=0.01)
            print(f"✅ Real trading enabled - Current balance: ${balance:.2f} USDC")
        except Exception as e:
            print(f"⚠️  Warning: Could not verify balance: {e}")
    
    strategy = create_strategy(args.strategy)
    portfolio_manager = PortfolioManager(
        initial_balance=args.initial_balance or 1000.0,
        strategy=strategy,
        execute_real_orders=args.money,
        clob_client=clob_client,
        gamma_client=gamma_client,
    )
    print(f"💰 Trading enabled:")
    print(f"   Initial balance: ${portfolio_manager.get_balance():.2f} USDC")
    print(f"   Strategy: {strategy}")
    if args.money:
        print(f"   ⚠️  REAL MONEY MODE: Orders will be executed on Polymarket!")
    else:
        print(f"   Simulated trading mode (use --money to execute real orders)")
    print()
    
    return portfolio_manager, clob_client, gamma_client


def _check_market_expiration(
    portfolio_manager: PortfolioManager | None,
    market_expirations: dict[str, datetime],
    latest_ticks: dict[str, MarketTick],
    args: argparse.Namespace,
) -> bool:
    """Check for expired markets and settle positions.
    
    Returns:
        True if trading should stop (loss threshold exceeded), False otherwise
    """
    if not portfolio_manager:
        return False
    
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
            # Get positions before expiration to calculate cost basis
            portfolio = portfolio_manager.get_portfolio()
            positions_before: dict[Outcome, tuple[float, float]] = {}  # outcome -> (quantity, cost_basis)
            
            for (m_id, outcome), position in portfolio.positions.items():
                if m_id == expired_market_id:
                    cost_basis = position.quantity * position.avg_price
                    positions_before[outcome] = (position.quantity, cost_basis)
            
            # Determine winner based on highest price
            settlement_info = portfolio_manager.expire_positions(
                market_id=expired_market_id,
                up_price=up_tick.mid,
                down_price=down_tick.mid,
            )
            
            winner = settlement_info["winner"]
            positions_settled = settlement_info["positions_settled"]
            total_payout = settlement_info["total_payout"]
            
            # Check for losses exceeding $20 threshold (only in --money mode)
            should_stop = False
            if args.money:
                for outcome, (quantity, cost_basis) in positions_before.items():
                    if outcome == winner:
                        # Winning position: payout = quantity * 1.0, loss = cost_basis - payout
                        payout = quantity * 1.0
                        loss = cost_basis - payout
                    else:
                        # Losing position: payout = 0, loss = cost_basis
                        loss = cost_basis
                    
                    if loss > 20.0:
                        print(f"\n🛑 STOPPING TRADING: Single trade loss of ${loss:.2f} exceeds $20 threshold!")
                        print(f"   Market: {expired_market_id}")
                        print(f"   Outcome: {outcome}")
                        print(f"   Cost basis: ${cost_basis:.2f}")
                        print(f"   Loss: ${loss:.2f}")
                        should_stop = True
                        break
            
            print_market_expired(
                market_id=expired_market_id,
                winner=winner,
                up_price=up_tick.mid,
                down_price=down_tick.mid,
                positions_settled=positions_settled,
                total_payout=total_payout,
                balance=portfolio_manager.get_balance(),
            )
            
            if should_stop:
                return True
        
        # Remove from tracking
        del market_expirations[expired_market_id]
    
    return False


async def _handle_interval_change(
    args: argparse.Namespace,
    auto_refresh: bool,
    current_interval_id: str | None,
    market_slug: str,
    observers: list,
    observer_tasks: list,
    latest_ticks: dict[str, MarketTick],
    portfolio_manager: PortfolioManager | None,
    market_expirations: dict[str, datetime],
    outcomes_to_watch: list[str],
    secrets: PolymarketSecrets,
    bus: EventBus,
    store: MemoryTickStore,
) -> tuple[str, str | None] | None:
    """Handle interval change for auto-refresh mode."""
    if not auto_refresh:
        return market_slug, current_interval_id
    
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
                        # Get positions before expiration to calculate cost basis
                        portfolio = portfolio_manager.get_portfolio()
                        positions_before: dict[Outcome, tuple[float, float]] = {}
                        
                        for (m_id, outcome), position in portfolio.positions.items():
                            if m_id == market_slug:
                                cost_basis = position.quantity * position.avg_price
                                positions_before[outcome] = (position.quantity, cost_basis)
                        
                        settlement_info = portfolio_manager.expire_positions(
                            market_id=market_slug,
                            up_price=up_tick.mid,
                            down_price=down_tick.mid,
                        )
                        winner = settlement_info["winner"]
                        total_payout = settlement_info["total_payout"]
                        print(f"   Settled expired market: {market_slug}")
                        print(f"   Winner: {winner}, Payout: ${total_payout:.2f} USDC")
                        
                        # Check for losses exceeding $20 threshold (only in --money mode)
                        if args.money:
                            for outcome, (quantity, cost_basis) in positions_before.items():
                                if outcome == winner:
                                    payout = quantity * 1.0
                                    loss = cost_basis - payout
                                else:
                                    loss = cost_basis
                                
                                if loss > 20.0:
                                    print(f"\n🛑 STOPPING TRADING: Single trade loss of ${loss:.2f} exceeds $20 threshold!")
                                    print(f"   Market: {market_slug}")
                                    print(f"   Outcome: {outcome}")
                                    print(f"   Cost basis: ${cost_basis:.2f}")
                                    print(f"   Loss: ${loss:.2f}")
                                    return market_slug, current_interval_id
        
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
        new_observers, new_observer_tasks = await create_observers(
            market_slug, outcomes_to_watch, secrets, args.frequency, bus, store
        )
        observers[:] = new_observers
        observer_tasks[:] = new_observer_tasks
        
        print(f"✅ Now watching: {market_slug}")
        print()
    
    return market_slug, current_interval_id


def _process_tick_for_trading(
    tick: MarketTick,
    portfolio_manager: PortfolioManager | None,
    latest_ticks: dict[str, MarketTick],
    last_successful_tick_time: dict[str, float],
    market_expirations: dict[str, datetime],
    count: int,
) -> tuple[bool, object | None]:
    """Process tick for trading if conditions are met."""
    if not portfolio_manager:
        return False, None
    
    up_tick = latest_ticks.get("UP")
    down_tick = latest_ticks.get("DOWN")
    
    if not (up_tick and down_tick):
        return False, None
    
    # Only trade if we have both ticks AND they are recent (within 5 seconds)
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
        decision = portfolio_manager.process_prices(
            market_id=tick.market_id,
            up_price=up_tick.best_ask,
            down_price=down_tick.best_ask,
        )
        if decision:
            # Track expiration time for this market if not already tracked
            if tick.market_id not in market_expirations:
                expiration_time = MarketSlugGenerator.get_market_expiration_time(tick.market_id)
                if expiration_time:
                    market_expirations[tick.market_id] = expiration_time
            return True, decision
    else:
        # Skip trading if we don't have fresh data for both outcomes or timestamps don't match
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
    
    return False, None


async def watch_mode(args: argparse.Namespace) -> None:
    """Watch market prices and optionally execute trades."""
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
    
    # Initialize portfolio manager if trading is enabled
    portfolio_manager, clob_client, gamma_client = _setup_portfolio_manager(args, secrets)
    
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
    latest_ticks: dict[str, MarketTick] = {}
    # Track latest prices per market (for calculating portfolio value)
    market_prices: dict[tuple[str, Outcome], float] = {}
    # Track when we last successfully received a tick for each outcome (to detect API errors)
    last_successful_tick_time: dict[str, float] = {}
    
    # Print table header
    header = print_watch_header(outcomes_to_watch)
    
    try:
        count = 0
        check_interval_counter = 0  # Counter to check for interval changes periodically
        
        while True:
            tick = await tick_queue.get()
            count += 1
            check_interval_counter += 1
            
            # Check for expired markets and settle positions
            if portfolio_manager and check_interval_counter >= 10:
                should_stop = _check_market_expiration(
                    portfolio_manager, market_expirations, latest_ticks, args
                )
                if should_stop:
                    print("\n🛑 Stopping trading due to loss threshold exceeded.")
                    await stop_observers(observers, observer_tasks)
                    break
            
            # Check for interval change every 10 ticks (to avoid checking too frequently)
            if auto_refresh and check_interval_counter >= 10:
                check_interval_counter = 0
                result = await _handle_interval_change(
                    args,
                    auto_refresh,
                    current_interval_id,
                    market_slug,
                    observers,
                    observer_tasks,
                    latest_ticks,
                    portfolio_manager,
                    market_expirations,
                    outcomes_to_watch,
                    secrets,
                    bus,
                    store,
                )
                if result is None:
                    # Trading stopped due to loss threshold
                    print("\n🛑 Stopping trading due to loss threshold exceeded.")
                    await stop_observers(observers, observer_tasks)
                    break
                market_slug, current_interval_id = result
            
            # Store latest tick for this outcome
            outcome_key = tick.outcome
            latest_ticks[outcome_key] = tick
            # Store price for this market/outcome
            market_prices[(tick.market_id, tick.outcome)] = tick.mid
            # Mark that we successfully received a tick for this outcome
            last_successful_tick_time[outcome_key] = tick.ts
            
            # Process with portfolio manager if we have both UP and DOWN prices
            trade_executed, decision = _process_tick_for_trading(
                tick,
                portfolio_manager,
                latest_ticks,
                last_successful_tick_time,
                market_expirations,
                count,
            )
            
            # Display tick data
            print_tick_table(count, outcomes_to_watch, latest_ticks, header)
            
            # Show portfolio info if trading is enabled
            if portfolio_manager and len(outcomes_to_watch) > 1:
                print_portfolio_info(
                    portfolio_manager,
                    tick,
                    latest_ticks,
                    market_prices,
                    args.initial_balance or 1000.0,
                )
                
                if trade_executed:
                    print_trade_executed(decision, tick.market_id)
            
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
            print_final_portfolio_stats(
                portfolio_manager,
                market_prices,
                args.initial_balance or 1000.0,
            )

