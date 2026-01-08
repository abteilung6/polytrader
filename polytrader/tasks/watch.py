import asyncio
from collections.abc import Callable

from polytrader.adapters import create_adapter_factory
from polytrader.config import PolymarketSecrets
from polytrader.events import MARKET_CHANGE, TICKS, EventBus
from polytrader.logging_config import logger
from polytrader.market_discovery import MarketDiscoveryService
from polytrader.observer import create_observer_factory
from polytrader.store import MemoryTickStore
from polytrader.types import MarketChangeEvent, MarketTick


def default_tick_handler(tick: MarketTick, count: int) -> None:
    """Default handler for tick events - logs using structured logging."""
    market_short = tick.market_slug.split("-")[-1] if "-" in tick.market_slug else tick.market_slug
    logger.bind(
        market_slug=tick.market_slug,
        outcome=tick.outcome,
        count=count,
    ).info(
        "#{count:4d}  {market:15s}  {outcome:4s}  "
        "bid:{bid:.4f} ask:{ask:.4f} mid:{mid:.4f} spread:{spread:.4f}",
        count=count,
        market=market_short,
        outcome=tick.outcome,
        bid=tick.best_bid,
        ask=tick.best_ask,
        mid=tick.mid,
        spread=abs(tick.spread),
    )


def default_market_change_handler(event: MarketChangeEvent) -> None:
    """Default handler for market change events - logs using structured logging."""
    if event.old_market:
        old_short = event.old_market.split("-")[-1] if "-" in event.old_market else event.old_market
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(old_market=event.old_market, new_market=event.new_market).info(
            "🔄 Market: {old} → {new}", old=old_short, new=new_short
        )
    else:
        new_short = event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
        logger.bind(new_market=event.new_market).info("🚀 Started: {market}", market=new_short)


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

    # For watch mode, we only need adapter and observer - no model or order manager
    adapter_factory = create_adapter_factory(secrets, polling_frequency_hz=frequency)
    observer_factory = create_observer_factory(bus, store)

    # Get initial market
    market = await discovery.get_current_market(market_pattern)
    if not market:
        # If pattern doesn't match, try using it as a direct market slug
        market = market_pattern

    # Create adapter and observer
    adapter = adapter_factory(market)
    observer = observer_factory(adapter)

    tick_queue = bus.subscribe(TICKS)
    market_change_queue = bus.subscribe(MARKET_CHANGE)

    # Start observer (this will fetch ticks and publish them)
    observer_task = asyncio.create_task(observer.run())

    async def handle_ticks() -> None:
        """Handle tick events."""
        count = 0
        while True:
            tick = await tick_queue.get()
            count += 1
            tick_handler(tick, count)

            if limit and count >= limit:
                observer.stop()
                break

    async def handle_market_changes() -> None:
        """Handle market change events."""
        while True:
            event = await market_change_queue.get()
            market_change_handler(event)

    ticks_task = asyncio.create_task(handle_ticks())
    market_changes_task = asyncio.create_task(handle_market_changes())

    try:
        await asyncio.gather(observer_task, ticks_task, market_changes_task)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer_task.cancel()
        ticks_task.cancel()
        market_changes_task.cancel()
        try:
            await observer_task
            await ticks_task
            await market_changes_task
        except asyncio.CancelledError:
            pass
