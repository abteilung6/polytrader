"""Platform orchestrator: Manages multi-strategy platform lifecycle.

Per Platform_Proposal.md §3.1: PlatformOrchestrator loads all strategies
from registry, creates StrategyRunner per strategy, and manages paper/live lanes.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.db.models import StrategyRecord
from polytrader.events import EventBus
from polytrader.execution import ExecutionRouter
from polytrader.execution.paper import PaperExecutionAdapter
from polytrader.logging_config import logger
from polytrader.oms import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore
from polytrader.platform.registry import StrategyRegistry
from polytrader.platform.strategy_runner import StrategyRunner
from polytrader.platform.supervisor_registry import MarketSupervisorRegistry
from polytrader.store import IMarketDataStore
from polytrader.strategies import create_simple_threshold_factory
from polytrader.supervisor.market import MarketSupervisor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from polytrader.adapters import IMarketDataAdapter
    from polytrader.market_discovery import IMarketDiscoveryService
    from polytrader.observer import IObserver
    from polytrader.position_manager import IPositionManager
    from polytrader.strategies.base import IStrategy


def create_strategy_factory_from_config(
    strategy_config: dict,
    store: IMarketDataStore,
) -> Callable[[str], "IStrategy"]:
    """Create strategy factory from strategy config.

    Args:
        strategy_config: Strategy configuration dict (from StrategyRecord.config)
        store: Market data store

    Returns:
        Factory function that creates IStrategy instances

    Raises:
        ValueError: If strategy type is not supported
    """
    strategy_type = strategy_config.get("type", "simple_threshold")

    if strategy_type == "simple_threshold":
        buy_threshold = strategy_config.get("buy_threshold", 0.30)
        min_history = strategy_config.get("min_history", 30)
        return create_simple_threshold_factory(
            store=store,
            buy_threshold=buy_threshold,
            min_history=min_history,
        )
    else:
        raise ValueError(f"Unsupported strategy type: {strategy_type}")


class PlatformOrchestrator:
    """Manages multi-strategy platform lifecycle.

    Per Platform_Proposal.md §3.1:
    - Loads all strategies from registry on boot
    - Creates StrategyRunner per enabled strategy
    - Manages paper/live OMS and execution routers
    - Coordinates strategy lifecycle

    Attributes:
        _bus: Event bus for communication
        _store: Market data store
        _session: Database session for registry access
        _strategy_runners: Dict mapping strategy_id -> StrategyRunner
        _paper_oms: OMS core for paper trading
        _live_oms: OMS core for live trading
        _paper_execution: Execution router for paper trading
        _live_execution: Execution router for live trading
        _running: Whether orchestrator is active
    """

    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
        session: "AsyncSession",
        discovery_service: "IMarketDiscoveryService",
        adapter_factory: Callable[[str], "IMarketDataAdapter"],
        observer_factory: Callable[["IMarketDataAdapter"], "IObserver"],
        position_manager: "IPositionManager | None" = None,
        live_execution_router_factory: Callable[[], ExecutionRouter] | None = None,
    ) -> None:
        """Initialize platform orchestrator.

        Args:
            bus: Event bus for communication
            store: Market data store
            session: Database session for registry access
            discovery_service: Market discovery service
            adapter_factory: Factory for creating market data adapters
            observer_factory: Factory for creating observers
            position_manager: Position manager (optional)
            live_execution_router_factory: Factory for live execution router (optional)
        """
        self._bus = bus
        self._store = store
        self._session = session
        self._discovery_service = discovery_service
        self._adapter_factory = adapter_factory
        self._observer_factory = observer_factory
        self._position_manager = position_manager
        self._live_execution_router_factory = live_execution_router_factory

        # MarketSupervisorRegistry for shared supervisors (Commit 1.4)
        self._supervisor_registry = MarketSupervisorRegistry(
            discovery_service=discovery_service,
            adapter_factory=adapter_factory,
            observer_factory=observer_factory,
            bus=bus,
            store=store,
            position_manager=position_manager,
        )

        # Strategy runners (created in start())
        self._strategy_runners: dict[str, StrategyRunner] = {}

        # Pattern to strategies mapping (for supervisor sharing)
        self._pattern_to_strategies: dict[str, list[str]] = {}

        # Paper OMS and execution (always created)
        self._paper_oms: OMSCore | None = None
        self._paper_execution: ExecutionRouter | None = None

        # Live OMS and execution (created if live_execution_router_factory provided)
        self._live_oms: OMSCore | None = None
        self._live_execution: ExecutionRouter | None = None

        self._running = False
        self._oms_tasks: list[asyncio.Task] = []
        self._execution_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the platform orchestrator.

        Per Platform_Proposal.md §3.1:
        1. Load strategies from registry
        2. Create paper/live OMS and execution routers
        3. Create StrategyRunner per enabled strategy
        4. Start all strategy runners
        """
        if self._running:
            return

        self._running = True
        logger.info("Starting PlatformOrchestrator")

        try:
            # Step 1: Load strategies from registry
            registry = StrategyRegistry(self._session)
            strategies = await registry.list_strategies()

            total_count = len(strategies)
            enabled_count = sum(1 for s in strategies if s.enabled)
            logger.info(
                "Loaded strategies from registry: {total} total, {enabled} enabled",
                total=total_count,
                enabled=enabled_count,
            )

            # Step 2: Create paper OMS and execution
            await self._create_paper_lane()

            # Step 3: Create live OMS and execution (if factory provided)
            if self._live_execution_router_factory:
                await self._create_live_lane()

            # Step 4: Group strategies by market_pattern and create shared supervisors
            enabled_list = [s for s in strategies if s.enabled]
            logger.info(
                "Starting {count} enabled strategies...",
                count=len(enabled_list),
            )

            # Group strategies by market_pattern
            pattern_to_strategies: dict[str, list[StrategyRecord]] = {}
            for strategy in enabled_list:
                pattern = strategy.config.get("market_pattern", "btc-updown-15m")
                pattern_to_strategies.setdefault(pattern, []).append(strategy)

            logger.info(
                "Grouped strategies: {pattern_count} unique patterns, {strategy_count} strategies",
                pattern_count=len(pattern_to_strategies),
                strategy_count=len(enabled_list),
            )

            # Create shared supervisors for each pattern
            pattern_to_supervisor: dict[str, MarketSupervisor] = {}
            for pattern, pattern_strategies in pattern_to_strategies.items():
                supervisor = await self._supervisor_registry.get_or_create(pattern)
                pattern_to_supervisor[pattern] = supervisor
                self._pattern_to_strategies[pattern] = [s.strategy_id for s in pattern_strategies]
                logger.debug(
                    "Created shared supervisor for pattern '{pattern}' ({count} strategies)",
                    pattern=pattern,
                    count=len(pattern_strategies),
                )

            # Create and start StrategyRunner per enabled strategy
            started_count = 0
            failed_count = 0

            for idx, strategy in enumerate(enabled_list, 1):
                try:
                    # Get market pattern for this strategy
                    pattern = strategy.config.get("market_pattern", "btc-updown-15m")
                    supervisor = pattern_to_supervisor[pattern]

                    runner = await self._create_strategy_runner(strategy, supervisor)
                    await runner.start()
                    self._strategy_runners[strategy.strategy_id] = runner
                    started_count += 1

                    # Log progress every 10 strategies or for the last one
                    if idx % 10 == 0 or idx == len(enabled_list):
                        logger.info(
                            "Strategy startup progress: {started}/{total} started, {failed} failed",
                            started=started_count,
                            total=len(enabled_list),
                            failed=failed_count,
                        )
                    else:
                        # Log individual strategy at debug level to reduce noise
                        logger.debug(
                            "Started strategy runner: {strategy_id} ({name})",
                            strategy_id=strategy.strategy_id,
                            name=strategy.name,
                        )
                except Exception:
                    failed_count += 1
                    logger.exception(
                        "Failed to create/start strategy runner: {strategy_id}",
                        strategy_id=strategy.strategy_id,
                        error_class="fatal",
                    )
                    # Continue with other strategies even if one fails
                    continue

            logger.info(
                "PlatformOrchestrator started: {total} strategy runners active",
                total=len(self._strategy_runners),
            )
        except Exception:
            self._running = False
            logger.exception("Failed to start PlatformOrchestrator", error_class="fatal")
            raise

    async def stop(self) -> None:
        """Stop the platform orchestrator.

        Stops all strategy runners, releases shared supervisors, and stops
        OMS/execution components gracefully.
        """
        if not self._running:
            return

        self._running = False
        logger.info("Stopping PlatformOrchestrator")

        try:
            # Stop all strategy runners
            stop_tasks = [
                runner.stop() for runner in self._strategy_runners.values() if runner.is_running()
            ]
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)

            # Release all shared supervisors (registry manages lifecycle)
            for pattern in list(self._pattern_to_strategies.keys()):
                await self._supervisor_registry.release(pattern)
            self._pattern_to_strategies.clear()

            # Stop all supervisors (registry will stop when ref_count reaches 0)
            await self._supervisor_registry.stop_all()

            # Stop OMS and execution tasks
            all_tasks = self._oms_tasks + self._execution_tasks
            for task in all_tasks:
                task.cancel()
            if all_tasks:
                await asyncio.gather(
                    *all_tasks,
                    return_exceptions=True,
                )

            logger.info("PlatformOrchestrator stopped")
        except Exception:
            logger.exception("Error stopping PlatformOrchestrator", error_class="fatal")
            raise

    async def _create_paper_lane(self) -> None:
        """Create paper OMS and execution router.

        Paper lane is always created for all strategies.
        """
        # Create paper OMS
        paper_oms_store = InMemoryOrderStore(self._bus)
        paper_idempotency = IdempotencyStore()
        self._paper_oms = OMSCore(
            bus=self._bus,
            store=paper_oms_store,
            idempotency_store=paper_idempotency,
        )

        # Create paper execution router
        paper_adapter = PaperExecutionAdapter(
            bus=self._bus,
            store=self._store,
        )
        self._paper_execution = ExecutionRouter(
            bus=self._bus,
            adapter=paper_adapter,
            is_paper_mode=True,
        )

        # Start OMS and execution
        self._oms_tasks.append(asyncio.create_task(self._paper_oms.run()))
        self._execution_tasks.append(asyncio.create_task(self._paper_execution.run()))

        logger.info("Created paper lane (OMS + execution)")

    async def _create_live_lane(self) -> None:
        """Create live OMS and execution router.

        Live lane is only created if live_execution_router_factory is provided.
        """
        if not self._live_execution_router_factory:
            return

        # Create live OMS
        live_oms_store = InMemoryOrderStore(self._bus)
        live_idempotency = IdempotencyStore()
        self._live_oms = OMSCore(
            bus=self._bus,
            store=live_oms_store,
            idempotency_store=live_idempotency,
        )

        # Create live execution router (from factory)
        self._live_execution = self._live_execution_router_factory()

        # Start OMS and execution
        self._oms_tasks.append(asyncio.create_task(self._live_oms.run()))
        self._execution_tasks.append(asyncio.create_task(self._live_execution.run()))

        logger.info("Created live lane (OMS + execution)")

    async def _create_strategy_runner(
        self,
        strategy: StrategyRecord,
        market_supervisor: MarketSupervisor,
    ) -> StrategyRunner:
        """Create StrategyRunner for a strategy with shared MarketSupervisor.

        Args:
            strategy: StrategyRecord from registry
            market_supervisor: Shared MarketSupervisor instance (already started)

        Returns:
            StrategyRunner instance

        Raises:
            ValueError: If strategy type is not supported
        """
        # Create strategy factory from config
        strategy_factory = create_strategy_factory_from_config(
            strategy_config=strategy.config,
            store=self._store,
        )

        # Create runner with shared supervisor
        runner = StrategyRunner(
            strategy=strategy,
            bus=self._bus,
            store=self._store,
            market_supervisor=market_supervisor,
            strategy_factory=strategy_factory,
            position_manager=self._position_manager,
        )

        return runner

    def get_strategy_runner(self, strategy_id: str) -> StrategyRunner | None:
        """Get strategy runner by ID.

        Args:
            strategy_id: Strategy identifier

        Returns:
            StrategyRunner if found, None otherwise
        """
        return self._strategy_runners.get(strategy_id)

    def list_strategy_runners(self) -> dict[str, StrategyRunner]:
        """List all strategy runners.

        Returns:
            Dict mapping strategy_id -> StrategyRunner
        """
        return self._strategy_runners.copy()

    def is_running(self) -> bool:
        """Check if orchestrator is active.

        Returns:
            True if running, False otherwise
        """
        return self._running

    async def add_strategy(self, strategy_id: str) -> None:
        """Add a strategy at runtime.

        Per Commit 2.1: Dynamically add a strategy without restarting the platform.
        Loads strategy from database, gets or creates shared supervisor for pattern,
        creates and starts StrategyRunner.

        Args:
            strategy_id: Strategy identifier to add

        Raises:
            ValueError: If strategy not found in database or not enabled
            RuntimeError: If orchestrator is not running

        Example:
            >>> await orchestrator.add_strategy("new_strategy")
        """
        if not self._running:
            raise RuntimeError("Cannot add strategy: orchestrator is not running")

        # Load strategy from database
        registry = StrategyRegistry(self._session)
        strategy = await registry.get_strategy(strategy_id)

        if strategy is None:
            raise ValueError(f"Strategy not found: {strategy_id}")

        if not strategy.enabled:
            raise ValueError(f"Strategy is not enabled: {strategy_id}")

        # Check if strategy already running (idempotent)
        if strategy_id in self._strategy_runners:
            logger.bind(strategy_id=strategy_id).debug(
                "Strategy already running, skipping add: {strategy_id}",
                strategy_id=strategy_id,
            )
            return

        try:
            # Get market pattern for this strategy
            pattern = strategy.config.get("market_pattern", "btc-updown-15m")

            # Get or create shared supervisor for pattern
            supervisor = await self._supervisor_registry.get_or_create(pattern)

            # Update pattern mapping
            if pattern not in self._pattern_to_strategies:
                self._pattern_to_strategies[pattern] = []
            if strategy_id not in self._pattern_to_strategies[pattern]:
                self._pattern_to_strategies[pattern].append(strategy_id)

            # Create and start StrategyRunner
            runner = await self._create_strategy_runner(strategy, supervisor)
            await runner.start()
            self._strategy_runners[strategy_id] = runner

            logger.bind(
                strategy_id=strategy_id,
                pattern=pattern,
            ).info(
                "Added strategy at runtime: {strategy_id} (pattern: {pattern})",
                strategy_id=strategy_id,
                pattern=pattern,
            )
        except Exception:
            logger.bind(
                strategy_id=strategy_id,
                error_class="fatal",
            ).exception("Failed to add strategy at runtime: {strategy_id}")
            raise

    async def remove_strategy(self, strategy_id: str) -> None:
        """Remove a strategy at runtime.

        Per Commit 2.1: Dynamically remove a strategy without restarting the platform.
        Stops and removes StrategyRunner, releases supervisor reference.

        Args:
            strategy_id: Strategy identifier to remove

        Raises:
            RuntimeError: If orchestrator is not running

        Example:
            >>> await orchestrator.remove_strategy("old_strategy")
        """
        if not self._running:
            raise RuntimeError("Cannot remove strategy: orchestrator is not running")

        # Check if strategy is running
        runner = self._strategy_runners.get(strategy_id)
        if runner is None:
            logger.bind(strategy_id=strategy_id).debug(
                "Strategy not running, skipping remove: {strategy_id}",
                strategy_id=strategy_id,
            )
            return

        try:
            # Stop runner
            if runner.is_running():
                await runner.stop()

            # Get pattern for supervisor release
            pattern = runner.market_supervisor.pattern

            # Remove runner
            del self._strategy_runners[strategy_id]

            # Update pattern mapping
            if pattern in self._pattern_to_strategies:
                if strategy_id in self._pattern_to_strategies[pattern]:
                    self._pattern_to_strategies[pattern].remove(strategy_id)
                # Clean up empty pattern entry
                if not self._pattern_to_strategies[pattern]:
                    del self._pattern_to_strategies[pattern]

            # Release supervisor reference
            await self._supervisor_registry.release(pattern)

            logger.bind(
                strategy_id=strategy_id,
                pattern=pattern,
            ).info(
                "Removed strategy at runtime: {strategy_id} (pattern: {pattern})",
                strategy_id=strategy_id,
                pattern=pattern,
            )
        except Exception:
            logger.bind(
                strategy_id=strategy_id,
                error_class="fatal",
            ).exception("Failed to remove strategy at runtime: {strategy_id}")
            raise
