import logging

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import EventBus

logger = logging.getLogger(__name__)


class Observer:
    def __init__(self, bus: EventBus, adapter: IMarketDataAdapter) -> None:
        self.bus = bus
        self.adapter = adapter
        self._running = False

    async def run(self) -> None:
        self._running = True
        try:
            async for tick in self.adapter.ticks():
                if not self._running:
                    break
                await self.bus.publish("ticks", tick)
        except Exception as e:
            logger.error(f"Observer error: {e}", exc_info=True)
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
