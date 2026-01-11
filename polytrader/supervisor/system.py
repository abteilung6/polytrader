"""System supervisor: Manages global/system-wide service lifecycle.

Per two-supervisor architecture:
- SystemSupervisor manages: PortfolioService, RiskChecker, OMSCore, ExecutionRouter, PositionManager
- Ensures correct startup/shutdown order (subscribers before publishers)
"""

import asyncio
from collections.abc import Callable

from polytrader.events import EventBus
from polytrader.execution import ExecutionRouter
from polytrader.logging_config import logger
from polytrader.oms import OMSCore
from polytrader.portfolio import PortfolioService
from polytrader.position_manager import IPositionManager
from polytrader.risk import RiskChecker
from polytrader.store import IMarketDataStore


class SystemSupervisor:
    """Manages global/system-wide service lifecycle.

    Coordinates PortfolioService, RiskChecker, OMSCore, ExecutionRouter, PositionManager.
    Ensures correct startup/shutdown order (subscribers before publishers).

    Per flows.mdc:
    - PortfolioService subscribes to SIGNALS (must start first)
    - RiskChecker subscribes to PROPOSALS (must start before PortfolioService publishes)
    - OMSCore subscribes to APPROVED_PROPOSALS (must start before RiskChecker publishes)
    - ExecutionRouter subscribes to SUBMIT_ORDER_COMMANDS (must start before OMSCore publishes)
    - PositionManager runs in background (syncs positions)
    """

    def __init__(
        self,
        bus: EventBus,
        store: IMarketDataStore,
        portfolio_service_factory: Callable[[], PortfolioService],
        risk_checker_factory: Callable[[], RiskChecker],
        oms_core_factory: Callable[[], OMSCore],
        execution_router_factory: Callable[[], ExecutionRouter] | None = None,
        position_manager_factory: Callable[[], IPositionManager] | None = None,
    ) -> None:
        """Initialize system supervisor.

        Args:
            bus: Event bus for communication
            store: Market data store
            portfolio_service_factory: Factory for PortfolioService
            risk_checker_factory: Factory for RiskChecker
            oms_core_factory: Factory for OMSCore
            execution_router_factory: Factory for ExecutionRouter (optional, for predict mode)
            position_manager_factory: Factory for PositionManager (optional)
        """
        self.bus = bus
        self.store = store

        # Service factories
        self.portfolio_service_factory = portfolio_service_factory
        self.risk_checker_factory = risk_checker_factory
        self.oms_core_factory = oms_core_factory
        self.execution_router_factory = execution_router_factory
        self.position_manager_factory = position_manager_factory

        # Service instances (created in start())
        self.portfolio_service: PortfolioService | None = None
        self.risk_checker: RiskChecker | None = None
        self.oms_core: OMSCore | None = None
        self.execution_router: ExecutionRouter | None = None
        self.position_manager: IPositionManager | None = None

        # Service tasks
        self._running = False
        self._portfolio_task: asyncio.Task | None = None
        self._risk_checker_task: asyncio.Task | None = None
        self._oms_core_task: asyncio.Task | None = None
        self._execution_router_task: asyncio.Task | None = None
        self._position_manager_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start all global services in correct order.

        Order: PortfolioService → RiskChecker → OMS Core → ExecutionRouter → PositionManager
        (Subscribers before publishers)
        """
        if self._running:
            return

        self._running = True
        logger.info("Starting SystemSupervisor")

        # 1. PortfolioService subscribes to SIGNALS (must start first)
        self.portfolio_service = self.portfolio_service_factory()
        await self.portfolio_service.start()
        await asyncio.sleep(0.01)  # Ensure subscription is active
        logger.debug("PortfolioService started")

        # 2. RiskChecker subscribes to PROPOSALS (must start before PortfolioService publishes)
        self.risk_checker = self.risk_checker_factory()
        self._risk_checker_task = asyncio.create_task(self.risk_checker.run())
        await asyncio.sleep(0.01)  # Ensure subscription is active
        logger.debug("RiskChecker started")

        # 3. OMS Core subscribes to APPROVED_PROPOSALS (must start before RiskChecker publishes)
        self.oms_core = self.oms_core_factory()
        self._oms_core_task = asyncio.create_task(self.oms_core.run())
        await asyncio.sleep(0.01)  # Ensure subscription is active
        logger.debug("OMSCore started")

        # 4. ExecutionRouter subscribes to SUBMIT_ORDER_COMMANDS (if enabled)
        if self.execution_router_factory is not None:
            self.execution_router = self.execution_router_factory()
            self._execution_router_task = asyncio.create_task(self.execution_router.run())
            await asyncio.sleep(0.01)  # Ensure subscription is active
            logger.debug("ExecutionRouter started")

        # 5. PositionManager (background sync)
        if self.position_manager_factory is not None:
            self.position_manager = self.position_manager_factory()
            self._position_manager_task = asyncio.create_task(self.position_manager.run())
            logger.debug("PositionManager started")

        logger.info("SystemSupervisor started (all services running)")

    async def stop(self) -> None:
        """Stop all global services in reverse order."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping SystemSupervisor")

        # Stop in reverse order
        if self.position_manager:
            self.position_manager.stop()
        if self.execution_router:
            self.execution_router.stop()
        if self.oms_core:
            self.oms_core.stop()
        if self.risk_checker:
            self.risk_checker.stop()
        if self.portfolio_service:
            await self.portfolio_service.stop()

        # Cancel tasks
        tasks = [
            self._position_manager_task,
            self._execution_router_task,
            self._oms_core_task,
            self._risk_checker_task,
            self._portfolio_task,
        ]

        for task in tasks:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to complete
        if tasks:
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)

        # Clear references
        self._position_manager_task = None
        self._execution_router_task = None
        self._oms_core_task = None
        self._risk_checker_task = None
        self._portfolio_task = None

        logger.info("SystemSupervisor stopped")

    async def run(self) -> None:
        """Run supervisor (wait for services to complete).

        This will run until stopped or an error occurs.
        """
        if not self._running:
            raise RuntimeError("SystemSupervisor not started. Call start() first.")

        try:
            # Wait for all service tasks
            tasks = [
                t
                for t in [
                    self._risk_checker_task,
                    self._oms_core_task,
                    self._execution_router_task,
                    self._position_manager_task,
                ]
                if t is not None
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await self.stop()

    def get_position_manager(self) -> IPositionManager | None:
        """Get position manager (for MarketSupervisor to query).

        Returns:
            Position manager instance, or None if not created
        """
        return self.position_manager
