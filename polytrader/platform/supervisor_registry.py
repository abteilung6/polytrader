"""MarketSupervisor registry with reference counting.

Per Commit 1.2: Registry manages shared MarketSupervisor instances.
Multiple strategies can share the same MarketSupervisor for the same market pattern.

Responsibilities:
- Create MarketSupervisor instances in strategy-less mode
- Track reference counts per pattern
- Destroy supervisors when ref_count reaches 0
- Provide cleanup method (stop_all)

Per architecture.md: Registry is a factory/manager, no business logic.
Per flow.md: Registry is part of PlatformOrchestrator, not trading pipeline.
"""

from collections.abc import Callable

from polytrader.adapters import IMarketDataAdapter
from polytrader.events import EventBus
from polytrader.logging_config import logger
from polytrader.market_discovery import IMarketDiscoveryService
from polytrader.observer import IObserver
from polytrader.position_manager import IPositionManager
from polytrader.store import IMarketDataStore
from polytrader.supervisor.market import MarketSupervisor


class MarketSupervisorRegistry:
    """Registry for managing shared MarketSupervisor instances.

    Provides reference counting to ensure supervisors are only destroyed
    when no longer in use. Creates supervisors in strategy-less mode
    (strategy_factory=None) so they can be shared by multiple StrategyRunner
    instances.

    Example:
        >>> registry = MarketSupervisorRegistry(
        ...     discovery_service=discovery,
        ...     adapter_factory=adapter_factory,
        ...     observer_factory=observer_factory,
        ...     bus=bus,
        ...     store=store,
        ... )
        >>> supervisor = await registry.get_or_create("btc-updown-15m")
        >>> # Use supervisor...
        >>> await registry.release("btc-updown-15m")
    """

    def __init__(
        self,
        discovery_service: IMarketDiscoveryService,
        adapter_factory: Callable[[str], IMarketDataAdapter],
        observer_factory: Callable[[IMarketDataAdapter], IObserver],
        bus: EventBus,
        store: IMarketDataStore,
        position_manager: IPositionManager | None = None,
    ) -> None:
        """Initialize the registry.

        Args:
            discovery_service: Service for finding active markets
            adapter_factory: Factory function to create adapters
            observer_factory: Factory function to create observers
            bus: Event bus for communication
            store: Market data store for historical data
            position_manager: Position manager reference (optional)
        """
        self.discovery_service = discovery_service
        self.adapter_factory = adapter_factory
        self.observer_factory = observer_factory
        self.bus = bus
        self.store = store
        self.position_manager = position_manager

        # Internal state: pattern -> (supervisor, ref_count)
        self._supervisors: dict[str, MarketSupervisor] = {}
        self._ref_counts: dict[str, int] = {}

    async def get_or_create(self, pattern: str) -> MarketSupervisor:
        """Get or create a MarketSupervisor for the given pattern.

        If a supervisor for this pattern already exists, returns the existing
        instance and increments the reference count. Otherwise, creates a new
        supervisor in strategy-less mode and starts it.

        Args:
            pattern: Market pattern (e.g., "btc-updown-15m")

        Returns:
            MarketSupervisor instance (shared, already started)

        Example:
            >>> supervisor = await registry.get_or_create("btc-updown-15m")
            >>> assert supervisor.strategy_factory is None  # Strategy-less mode
        """
        if pattern not in self._supervisors:
            # Create new supervisor in strategy-less mode
            supervisor = MarketSupervisor(
                pattern=pattern,
                discovery_service=self.discovery_service,
                adapter_factory=self.adapter_factory,
                observer_factory=self.observer_factory,
                bus=self.bus,
                store=self.store,
                strategy_factory=None,  # Strategy-less mode
                position_manager=self.position_manager,
            )
            await supervisor.start()
            self._supervisors[pattern] = supervisor
            self._ref_counts[pattern] = 0

        # Increment ref count
        self._ref_counts[pattern] += 1

        logger.debug(
            "MarketSupervisorRegistry: get_or_create pattern={pattern}, ref_count={ref_count}",
            pattern=pattern,
            ref_count=self._ref_counts[pattern],
        )

        return self._supervisors[pattern]

    async def release(self, pattern: str) -> None:
        """Release a reference to a MarketSupervisor.

        Decrements the reference count for the given pattern. If the ref_count
        reaches 0, stops and removes the supervisor.

        Args:
            pattern: Market pattern to release

        Example:
            >>> await registry.release("btc-updown-15m")
            >>> assert registry.get_ref_count("btc-updown-15m") == 0
        """
        if pattern not in self._ref_counts:
            return

        self._ref_counts[pattern] -= 1

        if self._ref_counts[pattern] == 0:
            # Stop and remove supervisor
            supervisor = self._supervisors.pop(pattern)
            supervisor.stop()  # stop() is synchronous
            del self._ref_counts[pattern]

            logger.debug(
                "MarketSupervisorRegistry: released and stopped pattern={pattern}",
                pattern=pattern,
            )
        else:
            logger.debug(
                "MarketSupervisorRegistry: released pattern={pattern}, ref_count={ref_count}",
                pattern=pattern,
                ref_count=self._ref_counts[pattern],
            )

    async def stop_all(self) -> None:
        """Stop all supervisors and clear the registry.

        Stops all registered supervisors and clears internal state.
        Useful for cleanup during shutdown.

        Example:
            >>> await registry.stop_all()
            >>> assert len(registry._supervisors) == 0
        """
        # Stop all supervisors
        for _pattern, supervisor in list(self._supervisors.items()):
            supervisor.stop()  # stop() is synchronous

        # Clear state
        self._supervisors.clear()
        self._ref_counts.clear()

        logger.info("MarketSupervisorRegistry: stopped all supervisors")

    def get_ref_count(self, pattern: str) -> int:
        """Get the reference count for a pattern.

        Args:
            pattern: Market pattern

        Returns:
            Reference count (0 if pattern not in registry)

        Example:
            >>> count = registry.get_ref_count("btc-updown-15m")
            >>> assert count >= 0
        """
        return self._ref_counts.get(pattern, 0)
