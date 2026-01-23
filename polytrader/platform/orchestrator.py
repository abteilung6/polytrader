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
from polytrader.store import IMarketDataStore
from polytrader.strategies import create_simple_threshold_factory

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

        # Strategy runners (created in start())
        self._strategy_runners: dict[str, StrategyRunner] = {}

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

            # Step 4: Create and start StrategyRunner per enabled strategy
            enabled_list = [s for s in strategies if s.enabled]
            logger.info(
                "Starting {count} enabled strategies...",
                count=len(enabled_list),
            )

            started_count = 0
            failed_count = 0

            for idx, strategy in enumerate(enabled_list, 1):
                try:
                    runner = await self._create_strategy_runner(strategy)
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

        Stops all strategy runners and OMS/execution components gracefully.
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
    ) -> StrategyRunner:
        """Create StrategyRunner for a strategy.

        Args:
            strategy: StrategyRecord from registry

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

        # Create runner
        runner = StrategyRunner(
            strategy=strategy,
            bus=self._bus,
            store=self._store,
            discovery_service=self._discovery_service,
            adapter_factory=self._adapter_factory,
            observer_factory=self._observer_factory,
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
