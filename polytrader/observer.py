from collections.abc import Callable
from typing import Protocol

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_DATA, EventBus
from polytrader.events.types import MarketDataEvent
from polytrader.logging_config import logger
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

    async def run(self) -> None:
        self._running = True
        try:
            async for tick in self.adapter.ticks():
                if not self._running:
                    break
                await self.publish_market_tick(tick)
        except Exception:
            logger.exception("Observer error")
            raise
        finally:
            self._running = False

    async def publish_market_tick(self, event: MarketDataEvent) -> None:
        """Publish a market data event to the bus and store.

        Args:
            event: Market data event to publish
        """
        self.store.add(event)
        await self.bus.publish(MARKET_DATA, event)
        logger.bind(
            market_slug=event.market_slug,
            outcome=event.outcome,
            bid=event.best_bid,
            ask=event.best_ask,
            mid=event.mid,
        ).info(
            "📊 {market_slug}/{outcome} bid={bid:.4f} ask={ask:.4f} mid={mid:.4f}",
            market_slug=event.market_slug,
            outcome=event.outcome,
            bid=event.best_bid,
            ask=event.best_ask,
            mid=event.mid,
        )

    def stop(self) -> None:
        self._running = False
