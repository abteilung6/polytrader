"""System supervisor: Manages global/system-wide service lifecycle.

Per two-supervisor architecture:
- SystemSupervisor manages: PortfolioService, RiskChecker, OMSCore, ExecutionRouter, PositionManager
- Ensures correct startup/shutdown order (subscribers before publishers)
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.types import ServiceErrorEvent, ServiceStartedEvent, ServiceStoppedEvent
from polytrader.execution import ExecutionRouter
from polytrader.logging_config import logger
from polytrader.oms import OMSCore
from polytrader.ops import CircuitBreaker, ExecutionControl, StateReconstructionService
from polytrader.portfolio import PortfolioService
from polytrader.position_manager import IPositionManager
from polytrader.risk import RiskChecker
from polytrader.store import IMarketDataStore
from polytrader.supervisor.errors import (
    FatalSupervisorError,
    RetryableSupervisorError,
    classify_service_error,
)
from polytrader.supervisor.metrics import (
    record_service_error,
    record_service_started,
    record_service_stopped,
    record_supervisor_startup_time,
    set_services_running,
)

SUPERVISOR_TYPE = "SystemSupervisor"
STARTUP_DELAY_S = 0.01  # Time between service starts (configurable)
STARTUP_TIMEOUT_S = 30.0  # Max time to start all services


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

    Per observability.mdc:
    - Emits ServiceStartedEvent, ServiceStoppedEvent, ServiceErrorEvent
    - Records metrics (startup time, service failures, services running)
    - Classifies errors (retryable vs fatal)
    - Structured logging with context
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
        user_stream_adapter_factory: Callable[[], Any] | None = None,
        reconciliation_service_factory: Callable[[], Any] | None = None,
        circuit_breaker_factory: Callable[[], CircuitBreaker] | None = None,
        execution_control: ExecutionControl | None = None,
        startup_delay_s: float = STARTUP_DELAY_S,
        startup_timeout_s: float = STARTUP_TIMEOUT_S,
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
            user_stream_adapter_factory: Factory for UserStreamAdapter (optional, for live trading)
            reconciliation_service_factory: Factory for ReconciliationService
                (optional, for live trading)
            circuit_breaker_factory: Factory for CircuitBreaker (optional, for live trading)
            execution_control: ExecutionControl instance (optional, for live trading)
            startup_delay_s: Time between service starts (default: 0.01s)
            startup_timeout_s: Max time to start all services (default: 30.0s)
        """
        self.bus = bus
        self.store = store

        # Service factories
        self.portfolio_service_factory = portfolio_service_factory
        self.risk_checker_factory = risk_checker_factory
        self.oms_core_factory = oms_core_factory
        self.execution_router_factory = execution_router_factory
        self.position_manager_factory = position_manager_factory
        self.user_stream_adapter_factory = user_stream_adapter_factory
        self.reconciliation_service_factory = reconciliation_service_factory
        self.circuit_breaker_factory = circuit_breaker_factory
        self._execution_control = execution_control

        # Configuration
        self.startup_delay_s = startup_delay_s
        self.startup_timeout_s = startup_timeout_s

        # Service instances (created in start())
        self.portfolio_service: PortfolioService | None = None
        self.risk_checker: RiskChecker | None = None
        self.oms_core: OMSCore | None = None
        self.execution_router: ExecutionRouter | None = None
        self.position_manager: IPositionManager | None = None

        # User stream and reconciliation components (optional, for live trading)
        self._user_stream_adapter: Any | None = None
        self._reconciliation_service: Any | None = None
        self._circuit_breaker: CircuitBreaker | None = None

        # Service tasks
        self._running = False
        self._risk_checker_task: asyncio.Task | None = None
        self._oms_core_task: asyncio.Task | None = None
        self._execution_router_task: asyncio.Task | None = None
        self._position_manager_task: asyncio.Task | None = None
        self._user_stream_task: asyncio.Task | None = None
        self._reconciliation_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start all global services in correct order.

        Order: PortfolioService → RiskChecker → OMS Core → ExecutionRouter → PositionManager
        (Subscribers before publishers)

        Per observability.mdc:
        - Emits ServiceStartedEvent for each service
        - Records metrics (startup time, service count)
        - Classifies errors (retryable vs fatal)
        - Uses timeouts to prevent hanging
        """
        if self._running:
            return

        startup_start = time.perf_counter()
        self._running = True

        logger.bind(supervisor=SUPERVISOR_TYPE).info("Starting SystemSupervisor")

        services_started = 0

        try:
            # 1. PortfolioService subscribes to SIGNALS (must start first)
            portfolio_service = self.portfolio_service_factory()
            self.portfolio_service = portfolio_service
            await self._start_service(
                "PortfolioService",
                portfolio_service,
                lambda: portfolio_service.start(),
            )
            services_started += 1

            # 2. RiskChecker subscribes to PROPOSALS (must start before PortfolioService publishes)
            risk_checker = self.risk_checker_factory()
            self.risk_checker = risk_checker
            await self._start_service_task(
                "RiskChecker",
                risk_checker,
                lambda: risk_checker.run(),
                lambda task: setattr(self, "_risk_checker_task", task),
            )
            services_started += 1

            # 3. OMS Core subscribes to APPROVED_PROPOSALS (must start before RiskChecker publishes)
            oms_core = self.oms_core_factory()
            self.oms_core = oms_core

            # 3a. State reconstruction (Phase 7) - rebuild from event log before starting OMS
            # Only for live trading (paper trading doesn't need this)
            if self.position_manager_factory is not None and self.bus._store is not None:
                logger.info("Starting state reconstruction from event log")
                try:
                    # Get OMS store from OMS core for state reconstruction
                    oms_store = oms_core.get_store()

                    # Get position manager (create but don't start yet)
                    position_manager = self.position_manager_factory()

                    # Create reconstruction service
                    reconstruction_service = StateReconstructionService(
                        event_store=self.bus._store,
                        oms_store=oms_store,
                        position_manager=position_manager,
                    )

                    # Reconstruct state
                    await reconstruction_service.reconstruct_all()

                    logger.info("State reconstruction complete")
                except Exception as e:
                    logger.exception(
                        "Error during state reconstruction: {error}",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Continue with startup even if reconstruction fails
                    # (system can still operate, just without historical state)

            await self._start_service_task(
                "OMSCore",
                oms_core,
                lambda: oms_core.run(),
                lambda task: setattr(self, "_oms_core_task", task),
            )
            services_started += 1

            # 4. ExecutionRouter subscribes to SUBMIT_ORDER_COMMANDS (if enabled)
            if self.execution_router_factory is not None:
                execution_router = self.execution_router_factory()
                self.execution_router = execution_router
                await self._start_service_task(
                    "ExecutionRouter",
                    execution_router,
                    lambda: execution_router.run(),
                    lambda task: setattr(self, "_execution_router_task", task),
                )
                services_started += 1

            # 5. PositionManager (background sync)
            if self.position_manager_factory is not None:
                position_manager = self.position_manager_factory()
                self.position_manager = position_manager
                await self._start_service_task(
                    "PositionManager",
                    position_manager,
                    lambda: position_manager.run(),
                    lambda task: setattr(self, "_position_manager_task", task),
                )
                services_started += 1

            # 6. UserStreamAdapter (for live trading, after OMS Core)
            if self.user_stream_adapter_factory is not None:
                user_stream_adapter = self.user_stream_adapter_factory()
                self._user_stream_adapter = user_stream_adapter
                await self._start_service_task(
                    "UserStreamAdapter",
                    user_stream_adapter,
                    lambda: user_stream_adapter.run(),
                    lambda task: setattr(self, "_user_stream_task", task),
                )
                services_started += 1

            # 7. ReconciliationService (for live trading, after OMS Core and ExecutionRouter)
            if self.reconciliation_service_factory is not None:
                reconciliation_service = self.reconciliation_service_factory()
                self._reconciliation_service = reconciliation_service
                await self._start_reconciliation_task(reconciliation_service)
                services_started += 1

            # 8. CircuitBreaker (for live trading, monitors reconciliation)
            if self.circuit_breaker_factory is not None:
                circuit_breaker = self.circuit_breaker_factory()
                self._circuit_breaker = circuit_breaker
                await self._start_service(
                    "CircuitBreaker",
                    circuit_breaker,
                    lambda: asyncio.sleep(0),  # Circuit breaker doesn't need async start
                )
                services_started += 1

            # Record total startup time
            startup_time_ms = (time.perf_counter() - startup_start) * 1000
            record_supervisor_startup_time(SUPERVISOR_TYPE, startup_time_ms)
            set_services_running(SUPERVISOR_TYPE, services_started)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                services_started=services_started,
                startup_time_ms=startup_time_ms,
            ).info(
                "SystemSupervisor started (all {count} services running in {time_ms:.1f}ms)",
                count=services_started,
                time_ms=startup_time_ms,
            )

        except Exception as e:
            # Classify and handle error
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                error_type=error_type,
                error_class=error_class,
                services_started=services_started,
            ).exception(
                "Failed to start SystemSupervisor: {error}",
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name="SystemSupervisor",
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            # Record metric
            record_service_error("SystemSupervisor", SUPERVISOR_TYPE, error_type, error_class)

            # Re-raise with appropriate error class
            if error_class == "fatal":
                raise FatalSupervisorError(
                    f"Fatal error starting SystemSupervisor: {error_msg}"
                ) from e
            else:
                raise RetryableSupervisorError(
                    f"Retryable error starting SystemSupervisor: {error_msg}"
                ) from e

    async def _start_service(
        self,
        service_name: str,
        service: object,
        start_service: Callable[[], Awaitable[Any]],
    ) -> None:
        """Start a service with observability.

        Args:
            service_name: Name of the service
            service: Service instance (already created)
            start_service: Async function to start the service
        """
        service_start = time.perf_counter()

        try:
            # Start service with timeout
            start_coro = start_service()
            await asyncio.wait_for(start_coro, timeout=self.startup_timeout_s)

            # Wait for subscription to be active
            await asyncio.sleep(self.startup_delay_s)

            # Record metrics and emit event
            startup_time_ms = (time.perf_counter() - service_start) * 1000
            record_service_started(service_name, SUPERVISOR_TYPE, startup_time_ms)

            started_event = ServiceStartedEvent(
                service_name=service_name,
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=startup_time_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service=service_name,
                startup_time_ms=startup_time_ms,
            ).debug(
                "{service} started in {time_ms:.1f}ms",
                service=service_name,
                time_ms=startup_time_ms,
            )

        except TimeoutError:
            error_msg = f"Service {service_name} startup timed out after {self.startup_timeout_s}s"
            raise RetryableSupervisorError(error_msg) from None
        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service=service_name,
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to start {service}: {error}",
                service=service_name,
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name=service_name,
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            # Record metric
            record_service_error(service_name, SUPERVISOR_TYPE, error_type, error_class)

            # Re-raise with appropriate error class
            if error_class == "fatal":
                raise FatalSupervisorError(
                    f"Fatal error starting {service_name}: {error_msg}"
                ) from e
            else:
                raise RetryableSupervisorError(
                    f"Retryable error starting {service_name}: {error_msg}"
                ) from e

    async def _start_service_task(
        self,
        service_name: str,
        service: object,
        run_service: Callable[[], Coroutine[Any, Any, Any]],
        set_task: Callable[[asyncio.Task[Any]], None],
    ) -> None:
        """Start a service that runs in a task.

        Args:
            service_name: Name of the service
            service: Service instance (already created)
            run_service: Async function to run the service
            set_task: Function to set the task
        """
        service_start = time.perf_counter()

        try:
            # Start service task
            run_coro = run_service()
            task: asyncio.Task[Any] = asyncio.create_task(run_coro)
            set_task(task)

            # Wait for subscription to be active
            await asyncio.sleep(self.startup_delay_s)

            # Record metrics and emit event
            startup_time_ms = (time.perf_counter() - service_start) * 1000
            record_service_started(service_name, SUPERVISOR_TYPE, startup_time_ms)

            started_event = ServiceStartedEvent(
                service_name=service_name,
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=startup_time_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service=service_name,
                startup_time_ms=startup_time_ms,
            ).debug(
                "{service} started in {time_ms:.1f}ms",
                service=service_name,
                time_ms=startup_time_ms,
            )

        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service=service_name,
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to start {service}: {error}",
                service=service_name,
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name=service_name,
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            # Record metric
            record_service_error(service_name, SUPERVISOR_TYPE, error_type, error_class)

            # Re-raise with appropriate error class
            if error_class == "fatal":
                raise FatalSupervisorError(
                    f"Fatal error starting {service_name}: {error_msg}"
                ) from e
            else:
                raise RetryableSupervisorError(
                    f"Retryable error starting {service_name}: {error_msg}"
                ) from e

    async def _start_reconciliation_task(self, reconciliation_service: Any) -> None:
        """Start reconciliation service as a periodic task.

        Args:
            reconciliation_service: ReconciliationService instance
        """
        service_start = time.perf_counter()
        reconciliation_interval_s = 60.0  # Reconcile every 60 seconds

        async def reconciliation_loop() -> None:
            """Periodic reconciliation loop."""
            try:
                # Wait a short time to ensure circuit breaker is initialized
                # (circuit breaker is created after reconciliation service in start())
                await asyncio.sleep(0.1)

                while self._running:
                    # Run reconciliation
                    reconcile_events = await reconciliation_service.reconcile()

                    # Check circuit breaker if configured
                    if self._circuit_breaker is not None:
                        await self._circuit_breaker.check(reconcile_events)

                    # Wait for next interval
                    await asyncio.sleep(reconciliation_interval_s)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="ReconciliationService",
                    error_type=type(e).__name__,
                ).exception("Error in reconciliation loop: {error}", error=str(e))

        try:
            # Start reconciliation task
            task = asyncio.create_task(reconciliation_loop())
            self._reconciliation_task = task

            # Wait for subscription to be active
            await asyncio.sleep(self.startup_delay_s)

            # Record metrics and emit event
            startup_time_ms = (time.perf_counter() - service_start) * 1000
            record_service_started("ReconciliationService", SUPERVISOR_TYPE, startup_time_ms)

            started_event = ServiceStartedEvent(
                service_name="ReconciliationService",
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=startup_time_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service="ReconciliationService",
                startup_time_ms=startup_time_ms,
            ).debug(
                "ReconciliationService started in {time_ms:.1f}ms",
                time_ms=startup_time_ms,
            )

        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service="ReconciliationService",
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to start ReconciliationService: {error}",
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name="ReconciliationService",
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            # Record metric
            record_service_error("ReconciliationService", SUPERVISOR_TYPE, error_type, error_class)

            # Re-raise with appropriate error class
            if error_class == "fatal":
                raise FatalSupervisorError(
                    f"Fatal error starting ReconciliationService: {error_msg}"
                ) from e
            else:
                raise RetryableSupervisorError(
                    f"Retryable error starting ReconciliationService: {error_msg}"
                ) from e

    async def stop(self) -> None:
        """Stop all global services in reverse order.

        Per observability.mdc:
        - Emits ServiceStoppedEvent for each service
        - Records metrics
        - Structured logging with context
        """
        if not self._running:
            return

        self._running = False
        logger.bind(supervisor=SUPERVISOR_TYPE).info("Stopping SystemSupervisor")

        services_stopped = 0

        # Stop in reverse order
        # Stop reconciliation task
        if self._reconciliation_task is not None:
            try:
                self._reconciliation_task.cancel()
                await asyncio.wait_for(self._reconciliation_task, timeout=5.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="ReconciliationService",
                    error_type=type(e).__name__,
                ).exception("Error stopping ReconciliationService: {error}", error=str(e))
            finally:
                record_service_stopped("ReconciliationService", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="ReconciliationService",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="ReconciliationService").debug(
                    "ReconciliationService stopped"
                )
                services_stopped += 1
                self._reconciliation_task = None

        # Stop user stream adapter
        if self._user_stream_adapter is not None:
            try:
                self._user_stream_adapter.stop()
                record_service_stopped("UserStreamAdapter", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="UserStreamAdapter",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="UserStreamAdapter").debug(
                    "UserStreamAdapter stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="UserStreamAdapter",
                    error_type=type(e).__name__,
                ).exception("Error stopping UserStreamAdapter: {error}", error=str(e))

        if self.position_manager is not None:
            try:
                self.position_manager.stop()
                record_service_stopped("PositionManager", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="PositionManager",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="PositionManager").debug(
                    "PositionManager stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="PositionManager",
                    error_type=type(e).__name__,
                ).exception("Error stopping PositionManager: {error}", error=str(e))

        if self.execution_router is not None:
            try:
                self.execution_router.stop()
                record_service_stopped("ExecutionRouter", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="ExecutionRouter",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="ExecutionRouter").debug(
                    "ExecutionRouter stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="ExecutionRouter",
                    error_type=type(e).__name__,
                ).exception("Error stopping ExecutionRouter: {error}", error=str(e))

        if self.oms_core is not None:
            try:
                self.oms_core.stop()
                record_service_stopped("OMSCore", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="OMSCore",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="OMSCore").debug("OMSCore stopped")
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="OMSCore",
                    error_type=type(e).__name__,
                ).exception("Error stopping OMSCore: {error}", error=str(e))

        if self.risk_checker is not None:
            try:
                self.risk_checker.stop()
                record_service_stopped("RiskChecker", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="RiskChecker",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="RiskChecker").debug(
                    "RiskChecker stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="RiskChecker",
                    error_type=type(e).__name__,
                ).exception("Error stopping RiskChecker: {error}", error=str(e))

        if self.portfolio_service is not None:
            try:
                await self.portfolio_service.stop()
                record_service_stopped("PortfolioService", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="PortfolioService",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="PortfolioService").debug(
                    "PortfolioService stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="PortfolioService",
                    error_type=type(e).__name__,
                ).exception("Error stopping PortfolioService: {error}", error=str(e))

        # Cancel tasks
        tasks = [
            self._reconciliation_task,
            self._user_stream_task,
            self._position_manager_task,
            self._execution_router_task,
            self._oms_core_task,
            self._risk_checker_task,
        ]

        for task in tasks:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to complete
        if tasks:
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)

        # Clear references
        self._reconciliation_task = None
        self._user_stream_task = None
        self._position_manager_task = None
        self._execution_router_task = None
        self._oms_core_task = None
        self._risk_checker_task = None

        set_services_running(SUPERVISOR_TYPE, 0)

        logger.bind(
            supervisor=SUPERVISOR_TYPE,
            services_stopped=services_stopped,
        ).info(
            "SystemSupervisor stopped ({count} services stopped)",
            count=services_stopped,
        )

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
                    self._user_stream_task,
                    self._reconciliation_task,
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
