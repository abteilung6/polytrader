"""Strategy runner: Manages a single strategy's lifecycle and routing.

Per Platform_Proposal.md §3.1: StrategyRunner wraps MarketSupervisor
and routes intents to paper/live lanes based on strategy activation.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.db.models import StrategyRecord
from polytrader.events import EventBus
from polytrader.logging_config import logger
from polytrader.store import IMarketDataStore
from polytrader.supervisor.market import MarketSupervisor

if TYPE_CHECKING:
    from polytrader.adapters import IMarketDataAdapter
    from polytrader.market_discovery import IMarketDiscoveryService
    from polytrader.observer import IObserver
    from polytrader.position_manager import IPositionManager
    from polytrader.strategies.base import IStrategy


class StrategyRunner:
    """Manages a single strategy's lifecycle and routing.

    Per Platform_Proposal.md §3.1:
    - Creates MarketSupervisor for the strategy
    - Routes intents to paper or live lane based on activation
    - Manages strategy lifecycle (start/stop)

    Attributes:
        strategy: StrategyRecord from registry
        market_supervisor: MarketSupervisor instance for this strategy
        bus: Event bus for communication
        store: Market data store
        _running: Whether the runner is active
    """

    def __init__(
        self,
        strategy: StrategyRecord,
        bus: EventBus,
        store: IMarketDataStore,
        discovery_service: "IMarketDiscoveryService",
        adapter_factory: Callable[[str], "IMarketDataAdapter"],
        observer_factory: Callable[["IMarketDataAdapter"], "IObserver"],
        strategy_factory: Callable[[str], "IStrategy"],
        position_manager: "IPositionManager | None" = None,
        market_pattern: str | None = None,
    ) -> None:
        """Initialize strategy runner.

        Args:
            strategy: StrategyRecord from registry
            bus: Event bus for communication
            store: Market data store
            discovery_service: Market discovery service
            adapter_factory: Factory for creating market data adapters
            observer_factory: Factory for creating observers
            strategy_factory: Factory for creating strategy instances
            position_manager: Position manager (optional)
            market_pattern: Market pattern (defaults to strategy.config.get("market_pattern"))
        """
        self.strategy = strategy
        self.bus = bus
        self.store = store
        self._running = False
        self._market_supervisor_task: asyncio.Task | None = None

        # Get market pattern from config or use default
        pattern = market_pattern or strategy.config.get("market_pattern", "btc-updown-15m")

        # Create MarketSupervisor for this strategy
        self.market_supervisor = MarketSupervisor(
            pattern=pattern,
            discovery_service=discovery_service,
            adapter_factory=adapter_factory,
            observer_factory=observer_factory,
            strategy_factory=strategy_factory,
            bus=bus,
            store=store,
            position_manager=position_manager,
        )

    async def start(self) -> None:
        """Start the strategy runner.

        Starts the MarketSupervisor for this strategy.
        """
        if self._running:
            return

        self._running = True
        logger.bind(
            strategy_id=self.strategy.strategy_id,
            strategy_name=self.strategy.name,
        ).info("Starting StrategyRunner")

        try:
            # Start MarketSupervisor
            await self.market_supervisor.start()

            # Start MarketSupervisor run loop
            self._market_supervisor_task = asyncio.create_task(self.market_supervisor.run())

            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
            ).info("StrategyRunner started")
        except Exception:
            self._running = False
            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
                error_class="fatal",
            ).exception("Failed to start StrategyRunner")
            raise

    async def stop(self) -> None:
        """Stop the strategy runner.

        Stops the MarketSupervisor gracefully.
        """
        if not self._running:
            return

        self._running = False
        logger.bind(
            strategy_id=self.strategy.strategy_id,
            strategy_name=self.strategy.name,
        ).info("Stopping StrategyRunner")

        try:
            # Stop MarketSupervisor
            self.market_supervisor.stop()

            # Cancel task if running
            if self._market_supervisor_task:
                self._market_supervisor_task.cancel()
                try:
                    await self._market_supervisor_task
                except asyncio.CancelledError:
                    pass

            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
            ).info("StrategyRunner stopped")
        except Exception:
            logger.bind(
                strategy_id=self.strategy.strategy_id,
                strategy_name=self.strategy.name,
                error_class="fatal",
            ).exception("Error stopping StrategyRunner")
            raise

    def is_running(self) -> bool:
        """Check if the runner is active.

        Returns:
            True if running, False otherwise
        """
        return self._running
