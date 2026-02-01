from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_DATA, EventBus
from polytrader.events.types import MarketDataEvent
from polytrader.logging_config import logger
from polytrader.obs.metrics import (
    record_md_gap,
    record_md_reconnect,
    record_md_staleness,
    record_md_update,
    set_md_book_mid,
    set_md_spread,
)
from polytrader.store import IMarketDataStore


class IObserver(Protocol):
    """Protocol for observer components."""

    async def run(self) -> None:
        """Start the observer."""
        ...

    def stop(self) -> None:
        """Stop the observer."""
        ...


def create_observer_factory(
    bus: EventBus,
    store: IMarketDataStore,
) -> Callable[[IMarketDataAdapter], IObserver]:
    """Create a factory function for IObserver.

    Args:
        bus: Event bus for publishing market data events
        store: Market data store for historical data

    Returns:
        Factory function that takes adapter and returns observer
    """

    def factory(adapter: IMarketDataAdapter) -> IObserver:
        return Observer(bus, adapter, store)

    return factory


class Observer(IObserver):
    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store: IMarketDataStore) -> None:
        self.bus = bus
        self.adapter = adapter
        self.store = store
        self._running = False
        # Track last update time per market/outcome for staleness calculation
        self._last_update_time: dict[tuple[str, str], datetime] = {}
        # Track if this is the first run (for reconnect metric)
        self._is_first_run = True
        # Gap detection threshold (seconds) - if time between updates exceeds this, it's a gap
        self._gap_threshold_seconds = 10.0

    async def run(self) -> None:
        self._running = True
        try:
            # Emit reconnect metric if this is not the first run
            if not self._is_first_run:
                record_md_reconnect()
            self._is_first_run = False

            async for tick in self.adapter.ticks():
                if not self._running:
                    break
                await self.publish_market_tick(tick)
        except Exception:
            logger.exception("Observer error")
            # Emit reconnect metric on error (connection lost)
            record_md_reconnect()
            raise
        finally:
            self._running = False

    async def publish_market_tick(self, event: MarketDataEvent) -> None:
        """Publish a market data event to the bus and store.

        Per observability.mdc §4: Emits market data metrics for monitoring.

        Args:
            event: Market data event to publish
        """
        # Parse event timestamp for staleness calculation
        try:
            event_time = datetime.fromisoformat(event.ts_wall.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Fallback to current time if parsing fails
            event_time = datetime.now(UTC)

        # Track last update time and detect gaps
        market_key = (event.market_slug, event.outcome)
        current_time = datetime.now(UTC)

        if market_key in self._last_update_time:
            last_time = self._last_update_time[market_key]
            time_diff = (event_time - last_time).total_seconds()

            # Detect gap if time between updates exceeds threshold
            if time_diff > self._gap_threshold_seconds:
                record_md_gap(market_slug=event.market_slug)

            # Calculate staleness: time since last update was received
            # This represents how "stale" the data was before this update
            staleness = (current_time - last_time).total_seconds()
            record_md_staleness(staleness_seconds=staleness, market_slug=event.market_slug)
        else:
            # First update for this market/outcome - no staleness yet
            record_md_staleness(staleness_seconds=0.0, market_slug=event.market_slug)

        # Update last update time (use current_time, not event_time, to track when we processed it)
        self._last_update_time[market_key] = current_time

        # Emit market data metrics per observability.mdc §4
        record_md_update(market_slug=event.market_slug, outcome=event.outcome)
        set_md_book_mid(mid=event.mid, market_slug=event.market_slug, outcome=event.outcome)
        set_md_spread(spread=event.spread, market_slug=event.market_slug, outcome=event.outcome)

        # Store and publish event
        self.store.add(event)
        await self.bus.publish(MARKET_DATA, event)
        logger.bind(
            market_slug=event.market_slug,
            outcome=event.outcome,
            bid=event.best_bid,
            ask=event.best_ask,
            mid=event.mid,
        ).debug(
            "📊 {market_slug}/{outcome} bid={bid:.4f} ask={ask:.4f} mid={mid:.4f}",
            market_slug=event.market_slug,
            outcome=event.outcome,
            bid=event.best_bid,
            ask=event.best_ask,
            mid=event.mid,
        )

    def stop(self) -> None:
        self._running = False
