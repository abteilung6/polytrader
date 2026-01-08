"""Market supervisor for managing component lifecycle and market transitions."""

import asyncio
import logging
import time
from collections.abc import Callable

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import MARKET_CHANGE, EventBus
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.models.protocol import ITradingModel
from polytrader.observer import IObserver
from polytrader.order_manager import IOrderManager
from polytrader.store import ITickStore
from polytrader.types import MarketChangeEvent

logger = logging.getLogger(__name__)


class MarketSupervisor:
    """Supervisor that manages component lifecycle and market transitions.

    Coordinates all trading components (Adapter, Observer, Model, OrderManager)
    and handles transitions when markets expire and new ones become active.
    """

    def __init__(
        self,
        pattern: str,
        discovery_service: IMarketDiscoveryService,
        adapter_factory: Callable[[str], IMarketDataAdapter],
        observer_factory: Callable[[IMarketDataAdapter], IObserver],
        model_factory: Callable[[str], ITradingModel],
        order_manager_factory: Callable[[], IOrderManager],
        bus: EventBus,
        store: ITickStore,
        monitor_interval: float = 30.0,
    ) -> None:
        """Initialize the market supervisor.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")
            discovery_service: Service for finding active markets
            adapter_factory: Factory function to create adapters
            observer_factory: Factory function to create observers
            model_factory: Factory function to create models
            order_manager_factory: Factory function to create order managers
            bus: Event bus for communication
            store: Tick store for historical data
            monitor_interval: How often to check for market changes (seconds)
        """
        self.pattern = pattern
        self.discovery = discovery_service
        self.adapter_factory = adapter_factory
        self.observer_factory = observer_factory
        self.model_factory = model_factory
        self.order_manager_factory = order_manager_factory
        self.bus = bus
        self.store = store
        self.monitor_interval = monitor_interval

        # Current state
        self.current_market: str | None = None
        self.adapter: IMarketDataAdapter | None = None
        self.observer: IObserver | None = None
        self.model: ITradingModel | None = None
        self.order_manager: IOrderManager | None = None

        # Tasks
        self._running = False
        self._observer_task: asyncio.Task | None = None
        self._model_task: asyncio.Task | None = None
        self._order_manager_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

    async def run(self) -> None:
        """Start the supervisor and manage component lifecycle."""
        self._running = True
        logger.info(f"Starting MarketSupervisor for pattern: {self.pattern}")

        # Initial market discovery
        market = await self.discovery.get_current_market(self.pattern)
        if not market:
            raise RuntimeError(f"No active market found for pattern: {self.pattern}")

        await self._transition_to_market(market)

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_market())

        try:
            # Wait for all tasks (filter out None)
            tasks = [
                t
                for t in [
                    self._observer_task,
                    self._model_task,
                    self._order_manager_task,
                    self._monitor_task,
                ]
                if t is not None
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await self._cleanup()

    async def _transition_to_market(self, new_market: str) -> None:
        """Transition all components to a new market.

        Stops all current components, then starts new ones with the new market.

        Args:
            new_market: Market slug to transition to
        """
        old_market = self.current_market

        if old_market == new_market:
            logger.debug(f"Already on market {new_market}, skipping transition")
            return

        logger.info(f"Transitioning from {old_market} to {new_market}")

        # Stop old components
        await self._stop_components()

        # Update current market
        self.current_market = new_market

        # Create new components
        self.adapter = self.adapter_factory(new_market)
        self.observer = self.observer_factory(self.adapter)
        self.model = self.model_factory(new_market)
        self.order_manager = self.order_manager_factory()

        # Start new components
        self._observer_task = asyncio.create_task(self.observer.run())
        self._model_task = asyncio.create_task(self.model.run())
        self._order_manager_task = asyncio.create_task(self.order_manager.run())

        # Publish market change event
        event = MarketChangeEvent(
            old_market=old_market,
            new_market=new_market,
            timestamp=time.time(),
        )
        await self.bus.publish(MARKET_CHANGE, event)

        logger.info(f"Successfully transitioned to market: {new_market}")

    async def _stop_components(self) -> None:
        """Stop all current components."""
        if self.observer:
            self.observer.stop()
        if self.model:
            self.model.stop()
        if self.order_manager:
            self.order_manager.stop()

        # Cancel tasks
        tasks = [
            self._observer_task,
            self._model_task,
            self._order_manager_task,
        ]

        for task in tasks:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to complete
        if tasks:
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)

        # Clear references
        self._observer_task = None
        self._model_task = None
        self._order_manager_task = None

    async def _monitor_market(self) -> None:
        """Monitor current market and detect expiration/transitions."""
        logger.info(f"Starting market monitor (checking every {self.monitor_interval}s)")

        while self._running:
            await asyncio.sleep(self.monitor_interval)

            try:
                # Check if current market is still active
                current = await self.discovery.get_current_market(self.pattern)

                if current and current != self.current_market:
                    # Market has changed
                    logger.info(f"Market change detected: {self.current_market} → {current}")
                    await self._transition_to_market(current)
                elif not current:
                    # No active market (gap between markets)
                    logger.warning("No active market found, waiting...")
                    # Retry in shorter interval
                    await asyncio.sleep(5.0)
            except Exception as e:
                logger.error(f"Error in market monitor: {e}", exc_info=True)
                # Continue monitoring despite errors

    async def _cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up MarketSupervisor")
        self._running = False

        # Cancel monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Stop all components
        await self._stop_components()

    def stop(self) -> None:
        """Stop the supervisor (non-blocking)."""
        self._running = False

    @property
    def current_market_slug(self) -> str | None:
        """Get current active market slug."""
        return self.current_market
