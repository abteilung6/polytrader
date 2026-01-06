import logging

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import TICKS, EventBus
from polytrader.store import ITickStore
from polytrader.types import MarketTick

logger = logging.getLogger(__name__)


class Observer:
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
