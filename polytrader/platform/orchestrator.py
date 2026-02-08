"""Platform orchestrator: Manages multi-strategy platform lifecycle.

Per Platform_Proposal.md §3.1: PlatformOrchestrator loads all strategies
from registry, creates StrategyRunner per strategy, and manages paper/live lanes.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from polytrader.config.models import PlatformConfig
from polytrader.db.models import StrategyRecord
from polytrader.events import (
    APPROVED_PROPOSALS_LIVE,
    APPROVED_PROPOSALS_PAPER,
    CANCEL_ORDER_COMMANDS_LIVE,
    CANCEL_ORDER_COMMANDS_PAPER,
    SUBMIT_ORDER_COMMANDS_LIVE,
    SUBMIT_ORDER_COMMANDS_PAPER,
    EventBus,
)
from polytrader.execution import ExecutionRouter
from polytrader.execution.paper import PaperExecutionAdapter
from polytrader.logging_config import logger
from polytrader.oms import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore
from polytrader.ops.control import ExecutionControl
from polytrader.platform.proposal_router import ApprovedProposalRouter
from polytrader.platform.registry import StrategyRegistry
from polytrader.platform.strategy_runner import StrategyRunner
from polytrader.platform.supervisor_registry import MarketSupervisorRegistry
from polytrader.portfolio.service import PortfolioService
from polytrader.risk.engine import RiskChecker, RiskEngine
from polytrader.store import IMarketDataStore, resolve_store_view
from polytrader.strategies.lifecycle_models import StrategyLifecycleState
from polytrader.strategies.registration import register_all_strategies
from polytrader.strategies.registry import StrategyRegistry as InMemoryStrategyRegistry
from polytrader.supervisor.market import MarketSupervisor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from polytrader.adapters import IMarketDataAdapter
    from polytrader.market_discovery import IMarketDiscoveryService
    from polytrader.observer import IObserver
    from polytrader.oms.store import IEventHandlingOrderStore
    from polytrader.position_manager import IPositionManager
    from polytrader.strategies.base import IStrategy


def create_strategy_factory_from_config(
    strategy: StrategyRecord,
    registry: InMemoryStrategyRegistry,
    store: IMarketDataStore,
) -> Callable[[str], "IStrategy"]:
    """Create strategy factory from strategy record using registry.

    Per architecture.mdc: Factory functions must use registry for discovery
    and validation. This function:
    1. Looks up template from registry using template_type_id and template_version
    2. Validates config against template's parameter schema
    3. Calls template's factory function with validated config

    Args:
        strategy: StrategyRecord with template_type_id, template_version, and config
        registry: In-memory StrategyRegistry with registered templates
        store: Market data store

    Returns:
        Factory function that creates IStrategy instances

    Raises:
        ValueError: If template not found, config validation fails, or factory creation fails
    """
    # Look up template from registry
    try:
        template = registry.get(strategy.template_type_id, strategy.template_version)
    except ValueError as e:
        msg = (
            f"Strategy template {strategy.template_type_id} "
            f"version {strategy.template_version} not found in registry"
        )
        raise ValueError(msg) from e

    # Extract orchestrator-level fields (not part of strategy parameter schema)
    # market_pattern is used by orchestrator for grouping strategies
    orchestrator_fields = {"market_pattern"}
    strategy_config = {k: v for k, v in strategy.config.items() if k not in orchestrator_fields}

    # Validate config against template's parameter schema
    validation_errors = template.parameter_schema.validate(strategy_config)
    if validation_errors:
        error_msg = "; ".join(validation_errors)
        raise ValueError(
            f"Config validation failed for strategy {strategy.strategy_id}: {error_msg}"
        )

    # Apply defaults to config (schema handles this)
    config_with_defaults = template.parameter_schema.apply_defaults(strategy_config)

    # Resolve store view per template: pattern (warm start) or slug (current market only).
    store_view = resolve_store_view(store, template.use_pattern_history)

    # Call template's factory function
    try:
        strategy_factory = template.factory(config_with_defaults, store_view)
        return strategy_factory
    except Exception as e:
        raise ValueError(f"Factory creation failed for strategy {strategy.strategy_id}: {e}") from e


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
        _portfolio_service: PortfolioService (converts signals to order intents)
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
        paper_oms_store: "IEventHandlingOrderStore | None" = None,
        platform_config: PlatformConfig | None = None,
        execution_control: ExecutionControl | None = None,
        get_active_strategies: Callable[[], set[str]] | None = None,
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
            paper_oms_store: Order store for paper OMS (must match position_manager's store)
            platform_config: Platform configuration (optional, defaults to PlatformConfig())
            execution_control: Execution control for proposal router (default: new instance)
            get_active_strategies: Callable returning active strategy IDs (default: empty set)
        """
        self._bus = bus
        self._execution_control = (
            execution_control if execution_control is not None else ExecutionControl()
        )
        self._get_active_strategies = (
            get_active_strategies if get_active_strategies is not None else (lambda: set())
        )
        self._store = store
        self._session = session
        self._discovery_service = discovery_service
        self._adapter_factory = adapter_factory
        self._observer_factory = observer_factory
        self._position_manager = position_manager
        self._live_execution_router_factory = live_execution_router_factory
        self._paper_oms_store = paper_oms_store
        self._platform_config = platform_config or PlatformConfig()

        # MarketSupervisorRegistry for shared supervisors (Commit 1.4)
        self._supervisor_registry = MarketSupervisorRegistry(
            discovery_service=discovery_service,
            adapter_factory=adapter_factory,
            observer_factory=observer_factory,
            bus=bus,
            store=store,
            position_manager=position_manager,
        )

        # PortfolioService to convert signals to order intents
        self._portfolio_service = PortfolioService(
            bus=bus,
            store=store,
            position_manager=position_manager,
            fixed_size_usd=self._platform_config.portfolio.fixed_size_usd,
        )

        # RiskChecker to check order intents and publish approved proposals
        risk_limits = self._platform_config.risk.to_risk_limits(
            version=self._platform_config.version
        )
        risk_engine = RiskEngine(limits=risk_limits)
        self._risk_checker = RiskChecker(
            bus=bus,
            engine=risk_engine,
            store=store,
        )

        # Strategy runners (created in start())
        self._strategy_runners: dict[str, StrategyRunner] = {}

        # Pattern to strategies mapping (for supervisor sharing)
        self._pattern_to_strategies: dict[str, list[str]] = {}

        # Proposal router (routes approved intents to paper/live topics)
        self._proposal_router: ApprovedProposalRouter | None = None

        # Paper OMS and execution (always created)
        self._paper_oms: OMSCore | None = None
        self._paper_execution: ExecutionRouter | None = None

        # Live OMS and execution (created if live_execution_router_factory provided)
        self._live_oms: OMSCore | None = None
        self._live_execution: ExecutionRouter | None = None

        self._running = False
        self._oms_tasks: list[asyncio.Task] = []
        self._execution_tasks: list[asyncio.Task] = []

        # In-memory strategy registry (initialized in start())
        self._strategy_template_registry: InMemoryStrategyRegistry | None = None

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
            # Step 0: Initialize in-memory strategy template registry
            self._strategy_template_registry = InMemoryStrategyRegistry()
            register_all_strategies(self._strategy_template_registry)
            logger.info(
                "Registered {count} strategy templates",
                count=len(self._strategy_template_registry.list_templates()),
            )

            # Step 1: Load strategy instances from database registry
            registry = StrategyRegistry(self._session)
            strategies = await registry.list_strategies()

            total_count = len(strategies)
            enabled_count = sum(
                1 for s in strategies if s.desired_state == StrategyLifecycleState.RUNNING
            )
            logger.info(
                "Loaded strategies from registry: {total} total, {enabled} enabled",
                total=total_count,
                enabled=enabled_count,
            )

            # Step 2: Start PortfolioService (converts signals to order intents)
            # Must start before OMS/execution so it can subscribe to SIGNALS
            await self._portfolio_service.start()
            logger.info("PortfolioService started")

            # Step 3: Start RiskChecker (checks order intents, publishes approved proposals)
            # Must start before PortfolioService publishes to PROPOSALS
            risk_task = asyncio.create_task(self._risk_checker.run())
            self._oms_tasks.append(risk_task)  # Track for cleanup
            logger.info("RiskChecker started")

            # Step 4: Start PositionManager (tracks positions from fills)
            if self._position_manager is not None:
                position_task = asyncio.create_task(self._position_manager.run())
                self._oms_tasks.append(position_task)  # Track for cleanup
                logger.info("PositionManager started")

            # Step 4b: Start ApprovedProposalRouter (routes approved intents to paper/live)
            self._proposal_router = ApprovedProposalRouter(
                bus=self._bus,
                execution_control=self._execution_control,
                get_active_strategies=self._get_active_strategies,
            )
            proposal_router_task = asyncio.create_task(self._proposal_router.run())
            self._oms_tasks.append(proposal_router_task)
            logger.info("ApprovedProposalRouter started")

            # Step 5: Create paper OMS and execution (lane topics)
            await self._create_paper_lane()

            # Step 5: Create live OMS and execution (if factory provided)
            if self._live_execution_router_factory:
                await self._create_live_lane()

            # Step 6: Group strategies by market_pattern and create shared supervisors
            enabled_list = [
                s for s in strategies if s.desired_state == StrategyLifecycleState.RUNNING
            ]
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

            # Stop PortfolioService
            await self._portfolio_service.stop()

            # Stop RiskChecker and proposal router
            self._risk_checker._running = False
            if self._proposal_router is not None:
                self._proposal_router.stop()
            # Their tasks are in _oms_tasks, will be cancelled below

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
        # Create paper OMS (use shared store if provided, otherwise create new one)
        if self._paper_oms_store is None:
            paper_oms_store: IEventHandlingOrderStore = InMemoryOrderStore(self._bus)
        else:
            paper_oms_store = self._paper_oms_store
        paper_idempotency = IdempotencyStore()
        self._paper_oms = OMSCore(
            bus=self._bus,
            store=paper_oms_store,
            idempotency_store=paper_idempotency,
            proposals_topic=APPROVED_PROPOSALS_PAPER,
            submit_commands_topic=SUBMIT_ORDER_COMMANDS_PAPER,
            cancel_commands_topic=CANCEL_ORDER_COMMANDS_PAPER,
        )

        # Create paper execution router (lane topics)
        paper_adapter = PaperExecutionAdapter(
            bus=self._bus,
            store=self._store,
        )
        self._paper_execution = ExecutionRouter(
            bus=self._bus,
            adapter=paper_adapter,
            is_paper_mode=True,
            submit_commands_topic=SUBMIT_ORDER_COMMANDS_PAPER,
            cancel_commands_topic=CANCEL_ORDER_COMMANDS_PAPER,
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

        # Create live OMS (lane topics)
        live_oms_store = InMemoryOrderStore(self._bus)
        live_idempotency = IdempotencyStore()
        self._live_oms = OMSCore(
            bus=self._bus,
            store=live_oms_store,
            idempotency_store=live_idempotency,
            proposals_topic=APPROVED_PROPOSALS_LIVE,
            submit_commands_topic=SUBMIT_ORDER_COMMANDS_LIVE,
            cancel_commands_topic=CANCEL_ORDER_COMMANDS_LIVE,
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
        # Create strategy factory from config using registry
        if self._strategy_template_registry is None:
            raise RuntimeError("Strategy template registry not initialized. Call start() first.")

        strategy_factory = create_strategy_factory_from_config(
            strategy=strategy,
            registry=self._strategy_template_registry,
            store=self._store,
        )

        # Create runner with shared supervisor
        runner = StrategyRunner(
            strategy=strategy,
            bus=self._bus,
            store=self._store,
            market_supervisor=market_supervisor,
            strategy_factory=strategy_factory,
            session=self._session,
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

        if strategy.desired_state != StrategyLifecycleState.RUNNING:
            raise ValueError(
                f"Strategy is not in RUNNING state: {strategy_id} "
                f"(current state: {strategy.desired_state})"
            )

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

            # Commit so actual_state (RUNNING) is visible to API state endpoints
            await self._session.commit()

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

            # Commit so actual_state (STOPPED) is visible to API state endpoints
            await self._session.commit()

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

    async def update_strategy(self, strategy_id: str) -> None:
        """Update a strategy at runtime.

        Per Commit 2.2: Dynamically update a strategy without restarting the platform.
        Detects pattern changes and migrates StrategyRunner to new supervisor if needed.

        Args:
            strategy_id: Strategy identifier to update

        Raises:
            ValueError: If strategy not found in database or not enabled
            RuntimeError: If orchestrator is not running

        Example:
            >>> await orchestrator.update_strategy("updated_strategy")
        """
        if not self._running:
            raise RuntimeError("Cannot update strategy: orchestrator is not running")

        # Load strategy from database
        registry = StrategyRegistry(self._session)
        strategy = await registry.get_strategy(strategy_id)

        if strategy is None:
            raise ValueError(f"Strategy not found: {strategy_id}")

        if strategy.desired_state != StrategyLifecycleState.RUNNING:
            raise ValueError(
                f"Strategy is not in RUNNING state: {strategy_id} "
                f"(current state: {strategy.desired_state})"
            )

        # Check if strategy is running
        runner = self._strategy_runners.get(strategy_id)
        if runner is None:
            # Strategy not running, just add it
            await self.add_strategy(strategy_id)
            return

        try:
            # Get current and new patterns
            old_pattern = runner.market_supervisor.pattern
            new_pattern = strategy.config.get("market_pattern", "btc-updown-15m")

            # Check if pattern changed
            if old_pattern == new_pattern:
                # Pattern unchanged, just update strategy record in runner
                # (StrategyRunner will use new config on next evaluation)
                runner.strategy = strategy
                logger.bind(
                    strategy_id=strategy_id,
                    pattern=new_pattern,
                ).debug(
                    "Updated strategy config (pattern unchanged): {strategy_id}",
                    strategy_id=strategy_id,
                )
                return

            # Pattern changed: migrate runner to new supervisor
            logger.bind(
                strategy_id=strategy_id,
                old_pattern=old_pattern,
                new_pattern=new_pattern,
            ).info(
                "Migrating strategy pattern: {strategy_id} ({old_pattern} → {new_pattern})",
                strategy_id=strategy_id,
                old_pattern=old_pattern,
                new_pattern=new_pattern,
            )

            # Stop current runner
            if runner.is_running():
                await runner.stop()

            # Release old supervisor
            await self._supervisor_registry.release(old_pattern)

            # Update pattern mapping
            if old_pattern in self._pattern_to_strategies:
                if strategy_id in self._pattern_to_strategies[old_pattern]:
                    self._pattern_to_strategies[old_pattern].remove(strategy_id)
                # Clean up empty pattern entry
                if not self._pattern_to_strategies[old_pattern]:
                    del self._pattern_to_strategies[old_pattern]

            # Get or create new supervisor
            new_supervisor = await self._supervisor_registry.get_or_create(new_pattern)

            # Update pattern mapping for new pattern
            if new_pattern not in self._pattern_to_strategies:
                self._pattern_to_strategies[new_pattern] = []
            if strategy_id not in self._pattern_to_strategies[new_pattern]:
                self._pattern_to_strategies[new_pattern].append(strategy_id)

            # Create new runner with new supervisor
            new_runner = await self._create_strategy_runner(strategy, new_supervisor)
            await new_runner.start()
            self._strategy_runners[strategy_id] = new_runner

            logger.bind(
                strategy_id=strategy_id,
                old_pattern=old_pattern,
                new_pattern=new_pattern,
            ).info(
                "Migrated strategy to new pattern: {strategy_id} ({old_pattern} → {new_pattern})",
                strategy_id=strategy_id,
                old_pattern=old_pattern,
                new_pattern=new_pattern,
            )
        except Exception:
            logger.bind(
                strategy_id=strategy_id,
                error_class="fatal",
            ).exception("Failed to update strategy at runtime: {strategy_id}")
            raise
