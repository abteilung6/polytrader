import logging
from collections.abc import Callable
from typing import Protocol

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import TICKS, EventBus
from polytrader.store import ITickStore
from polytrader.types import MarketTick

logger = logging.getLogger(__name__)


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
    store: ITickStore,
) -> Callable[[IMarketDataAdapter], IObserver]:
    """Create a factory function for IObserver.

    Args:
        bus: Event bus for publishing ticks
        store: Tick store for historical data

    Returns:
        Factory function that takes adapter and returns observer
    """

    def factory(adapter: IMarketDataAdapter) -> IObserver:
        return Observer(bus, adapter, store)

    return factory


class Observer(IObserver):
    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter, store: ITickStore) -> None:
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
        except Exception as e:
            logger.error(f"Observer error: {e}", exc_info=True)
            raise
        finally:
            self._running = False

    async def publish_market_tick(self, tick: MarketTick) -> None:
        self.store.add(tick)
        await self.bus.publish(TICKS, tick)

    def stop(self) -> None:
        self._running = False
