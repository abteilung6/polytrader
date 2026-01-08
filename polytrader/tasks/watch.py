import asyncio
from collections.abc import Callable
from datetime import datetime

from polytrader.adapters import create_adapter_factory
from polytrader.clob import create_clob_client_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import MARKET_CHANGE, TICKS, EventBus
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.models import create_model_factory
from polytrader.observer import create_observer_factory
from polytrader.order_manager import create_order_manager_factory
from polytrader.store import MemoryTickStore
from polytrader.supervisor import MarketSupervisor
from polytrader.types import MarketChangeEvent, MarketTick


def default_tick_handler(tick: MarketTick, count: int) -> None:
    """Default handler for tick events - prints to stdout."""
    print(f"Tick #{count}:")
    print(f"  Timestamp: {tick.ts:.3f}")
    print(f"  Market: {tick.market_slug}")
    print(f"  Outcome: {tick.outcome}")
    print(f"  Best Bid: {tick.best_bid:.4f}")
    print(f"  Best Ask: {tick.best_ask:.4f}")
    print(f"  Mid Price: {tick.mid:.4f}")
    print(f"  Spread: {tick.spread:.4f}")
    print()


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events - prints to stdout."""
    change_time = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    if event.old_market:
        print(f"\n🔄 Market transition at {change_time}:")
        print(f"   Old: {event.old_market}")
        print(f"   New: {event.new_market}\n")
    else:
        print(f"\n🚀 Started with market: {event.new_market} at {change_time}\n")


async def watch_task(
    market_pattern: str,
    frequency: float = 1.0,
    limit: int | None = None,
    tick_handler: Callable[[MarketTick, int], None] | None = None,
    market_change_handler: Callable[[MarketChangeEvent], None] | None = None,
    secrets: PolymarketSecrets | None = None,
) -> None:
    """Watch market ticks for a given pattern.

    Args:
        market_pattern: Market pattern (e.g., 'btc-updown-15m') or market slug
        frequency: Polling frequency in Hz
        limit: Number of ticks to show before stopping (None = unlimited)
        tick_handler: Callback for each tick (default: prints to stdout)
        market_change_handler: Callback for market changes (default: prints to stdout)
        secrets: Polymarket secrets (defaults to loading from env)
    """
    if secrets is None:
        secrets = PolymarketSecrets()

    if tick_handler is None:
        tick_handler = default_tick_handler

    if market_change_handler is None:
        market_change_handler = default_market_change_handler

    bus = EventBus()
    store = MemoryTickStore()
    discovery = MarketDiscoveryService()

    adapter_factory = create_adapter_factory(secrets, polling_frequency_hz=frequency)
    observer_factory = create_observer_factory(bus, store)
    model_factory = create_model_factory(bus, store)
    clob_client_factory = create_clob_client_factory(secrets)
    order_manager_factory = create_order_manager_factory(
        bus, clob_client_factory, max_trades_per_market=1
    )

    supervisor = MarketSupervisor(
        pattern=market_pattern,
        discovery_service=discovery,
        adapter_factory=adapter_factory,
        observer_factory=observer_factory,
        model_factory=model_factory,
        order_manager_factory=order_manager_factory,
        bus=bus,
        store=store,
    )

    tick_queue = bus.subscribe(TICKS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    supervisor_task = asyncio.create_task(supervisor.run())

    async def handle_ticks() -> None:
        """Handle tick events."""
        count = 0
        while True:
            tick = await tick_queue.get()
            count += 1
            tick_handler(tick, count)

            if limit and count >= limit:
                supervisor.stop()
                break

    async def handle_market_changes() -> None:
        """Handle market change events."""
        while True:
            event = await market_change_queue.get()
            market_change_handler(event)

    ticks_task = asyncio.create_task(handle_ticks())
    market_changes_task = asyncio.create_task(handle_market_changes())

    try:
        await asyncio.gather(supervisor_task, ticks_task, market_changes_task)
    except KeyboardInterrupt:
        supervisor.stop()
    finally:
        supervisor_task.cancel()
        ticks_task.cancel()
        market_changes_task.cancel()
        try:
            await supervisor_task
            await ticks_task
            await market_changes_task
        except asyncio.CancelledError:
            pass
