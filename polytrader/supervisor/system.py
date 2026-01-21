"""System supervisor: Manages global/system-wide service lifecycle.

Per two-supervisor architecture:
- SystemSupervisor manages: PortfolioService, RiskChecker, OMSCore, ExecutionRouter, PositionManager
- Ensures correct startup/shutdown order (subscribers before publishers)
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from polytrader.ops.health import HealthStatus
    from polytrader.ops.control_plane import ControlPlaneService

from polytrader.config import get_database_url, load_config
from polytrader.events import SYSTEM_LIFECYCLE, EventBus
from polytrader.events.sink import EventSink
from polytrader.events.stores import PostgreSQLEventStore
from polytrader.events.types import (
    ServiceErrorEvent,
    ServiceStartedEvent,
    ServiceStoppedEvent,
    SystemStartedEvent,
)
from polytrader.execution import ExecutionRouter
from polytrader.logging_config import logger
from polytrader.oms import OMSCore
from polytrader.ops import (
    CircuitBreaker,
    ExecutionControl,
    HealthGateThresholds,
    HealthService,
    StateReconstructionService,
)
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
        health_service_factory: Callable[[], HealthService] | None = None,
        health_gate_thresholds: HealthGateThresholds | None = None,
        config_path: str | None = None,
        control_command_path: str | None = None,
        control_poll_interval_s: float = 1.0,
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
            health_service_factory: Factory for HealthService (optional, for live trading)
            health_gate_thresholds: Health gate thresholds (optional, uses defaults if not provided)
            config_path: Path to config file (optional, for live trading)
            control_command_path: Path to runtime control command file (optional)
            control_poll_interval_s: Control plane poll interval in seconds
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
        self.health_service_factory = health_service_factory
        self.health_gate_thresholds = health_gate_thresholds or HealthGateThresholds()
        self.config_path = config_path
        self.control_command_path = control_command_path
        self.control_poll_interval_s = control_poll_interval_s

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

        # EventSink (mandatory, per proposal)
        self._event_sink: EventSink | None = None
        self._control_plane: "ControlPlaneService | None" = None

        # Health gate status (set during boot, used in commit 7 for execution permit)
        self._health_gates_passed: bool = True

        # Service tasks
        self._running = False
        self._risk_checker_task: asyncio.Task | None = None
        self._oms_core_task: asyncio.Task | None = None
        self._execution_router_task: asyncio.Task | None = None
        self._position_manager_task: asyncio.Task | None = None
        self._user_stream_task: asyncio.Task | None = None
        self._reconciliation_task: asyncio.Task | None = None
        self._event_sink_task: asyncio.Task | None = None
        self._control_plane_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start all global services following boot sequence.

        Per flows.mdc §2: Boot sequence with health checks and execution gating.

        Boot Sequence:
        1. Load config (validated). Emit ConfigLoadedEvent.
        2. Init event store. Emit SystemStartedEvent.
        3. Start adapters (market data, user stream).
        4. Build projections from event log (OMS, positions, PnL).
        5. Initial reconciliation snapshot.
        6. Health gates evaluation.
        7. Issue execution permit (if all gates pass).
        8. Start services (PortfolioService → RiskChecker → OMS Core →
           ExecutionRouter → PositionManager).

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

        try:
            # Boot sequence per flows.mdc §2
            # 1. Load config (if not already loaded)
            await self._load_config()

            # 2. Init event store (emit SystemStartedEvent)
            await self._init_event_store()

            # 2.5. Initialize EventSink (mandatory, per proposal)
            await self._init_event_sink()

            # 2.6. Initialize ControlPlane (optional, for runtime commands)
            await self._init_control_plane()

            # Create core components ONCE early (before boot steps that need them)
            # Per review: OMS core and position manager must be created once and reused
            # to ensure state reconstruction persists across boot sequence steps
            if self.oms_core_factory is not None:
                self.oms_core = self.oms_core_factory()
            if self.position_manager_factory is not None:
                self.position_manager = self.position_manager_factory()
            if self.execution_router_factory is not None:
                self.execution_router = self.execution_router_factory()

            # 3. Start adapters (market data, user stream)
            await self._start_adapters()

            # 4. Build projections from event log
            await self._reconstruct_state()

            # 5. Initial reconciliation snapshot
            initial_reconciliation_divergences = await self._initial_reconciliation()

            # 6. Health gates evaluation
            health_status = await self._evaluate_health_gates(initial_reconciliation_divergences)

            # 7. Issue execution permit (if all gates pass)
            if health_status is not None and self._health_gates_passed:
                await self._issue_execution_permit(health_status)
            elif not self._health_gates_passed:
                logger.error("Health gates failed, execution permit NOT issued")

            # 8. Start services (existing logic)
            services_started = await self._start_services()

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
            services_started = 0
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

    async def _load_config(self) -> dict[str, Any]:
        """Load configuration (if not already loaded).

        Per flows.mdc §2: Load config, validate, calculate hash, emit ConfigLoadedEvent.

        Returns:
            Configuration dictionary (empty dict if no config path provided)
        """
        if self.config_path is None:
            # Paper trading mode - config loading is optional
            logger.debug("Config loading skipped (no config_path provided)")
            return {}

        try:
            logger.info("Loading configuration from {path}", path=self.config_path)
            config = await load_config(config_path=self.config_path, bus=self.bus)
            logger.info("Configuration loaded successfully")
            return config
        except Exception as e:
            logger.exception(
                "Error loading configuration: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue with startup even if config loading fails
            # (system can operate with defaults)
            return {}

    async def _init_event_store(self) -> None:
        """Initialize event store and emit SystemStartedEvent.

        Per flows.mdc §2: Init EventStore (append-only), emit SystemStartedEvent.
        The run_id is explicitly generated and set in the event to ensure all
        events in this system run share the same run_id for correlation.
        """
        # Event store is already initialized when EventBus is created
        # Generate run_id and emit SystemStartedEvent with explicit run_id
        try:
            # Generate run_id for this system run
            # This ensures SystemStartedEvent has the run_id we log
            run_id = str(uuid.uuid4())

            # Create SystemStartedEvent with explicit run_id
            # This allows correlating all events from this system run
            started_event = SystemStartedEvent(run_id=run_id)
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            logger.info(
                "SystemStartedEvent emitted (run_id: {run_id})",
                run_id=run_id,
            )
        except Exception as e:
            logger.exception(
                "Error emitting SystemStartedEvent: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue with startup even if event emission fails

    async def _init_event_sink(self) -> None:
        """Initialize EventSink for asynchronous event persistence.

        Per proposal: EventSink is mandatory (no config check).
        Initializes PostgreSQL event store and EventSink.
        Errors are logged but do not prevent startup.
        """
        try:
            # Get database URL from config or environment
            # This may fail if database config is missing, which is OK
            try:
                database_url = get_database_url()
            except Exception as config_error:
                logger.warning(
                    "Database configuration not available: {error}. "
                    "EventSink will not be initialized.",
                    error=str(config_error),
                    error_type=type(config_error).__name__,
                )
                self._event_sink = None
                return

            # Create PostgreSQL event store
            event_store = PostgreSQLEventStore(connection_url=database_url, pool_size=10)
            await event_store.initialize()

            # Create EventSink
            self._event_sink = EventSink(bus=self.bus, store=event_store)

            logger.info("EventSink initialized successfully")
        except Exception as e:
            logger.exception(
                "Error initializing EventSink: {error}. "
                "System will continue without event persistence.",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue with startup even if EventSink initialization fails
            # (system can operate without event persistence, though not recommended)
            self._event_sink = None

    async def _init_control_plane(self) -> None:
        """Initialize ControlPlaneService for runtime commands."""
        if self.control_command_path is None:
            logger.debug("Control plane disabled (no command path configured)")
            return
        if self._execution_control is None:
            logger.warning("Control plane disabled (no execution control)")
            return

        from pathlib import Path

        from polytrader.ops.control_plane import ControlPlaneService, FileControlCommandReader

        command_path = Path(self.control_command_path)
        command_reader = FileControlCommandReader(command_path)
        self._control_plane = ControlPlaneService(
            bus=self.bus,
            command_reader=command_reader,
            execution_control=self._execution_control,
            store=self.store,
            health_gate_thresholds=self.health_gate_thresholds,
            poll_interval_s=self.control_poll_interval_s,
            get_user_stream_adapter=lambda: self._user_stream_adapter,
            get_circuit_breaker=lambda: self._circuit_breaker,
        )
        logger.info("Control plane initialized", command_path=str(command_path))

    async def _start_adapters(self) -> None:
        """Start adapters (market data, user stream).

        Per flows.mdc §2: Start adapters (market data WS, user stream WS, REST clients).

        Note: Market data adapter is started by MarketSupervisor, not SystemSupervisor.
        User stream adapter is created here but started later as a service.
        """
        # Market data adapter is started by MarketSupervisor
        # User stream adapter is created here but started later as a service
        # (it may be created earlier for health gate evaluation)
        logger.debug("Adapters will be started by MarketSupervisor and as services")

    async def _reconstruct_state(self) -> None:
        """Build projections from event log.

        Per flows.mdc §2: Build projections from event log (OMS, positions, PnL).

        Note: Only for live trading (paper trading doesn't need this).
        """
        # Only for live trading (paper trading doesn't need this)
        if self.position_manager_factory is None or self.bus._store is None:
            logger.debug("State reconstruction skipped (paper trading mode)")
            return

        logger.info("Starting state reconstruction from event log")
        try:
            # Use OMS core and position manager created early in boot sequence
            # Per review: Must reuse same instances to ensure reconstructed state persists
            if self.oms_core is None:
                logger.error("OMS core not initialized - cannot reconstruct state")
                return
            if self.position_manager is None:
                logger.error("Position manager not initialized - cannot reconstruct state")
                return

            oms_store = self.oms_core.get_store()

            # Create reconstruction service
            reconstruction_service = StateReconstructionService(
                event_store=self.bus._store,
                oms_store=oms_store,
                position_manager=self.position_manager,
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

    async def _initial_reconciliation(self) -> list[Any]:
        """Run initial reconciliation snapshot.

        Per flows.mdc §2: Initial reconciliation snapshot
        (fetch venue orders, compare to projections).

        Returns:
            List of reconciliation divergences (empty list if reconciliation skipped or failed)
        """
        # Only for live trading (paper trading doesn't need this)
        if self.reconciliation_service_factory is None or self.execution_router_factory is None:
            logger.debug("Initial reconciliation skipped (paper trading mode)")
            return []

        logger.info("Starting initial reconciliation snapshot")
        try:
            # Use execution router and OMS core created early in boot sequence
            # Per review: Must reuse same instances to ensure reconciliation operates
            # on the same store that was used for state reconstruction
            if self.execution_router is None:
                logger.error("Execution router not initialized - cannot perform reconciliation")
                return []
            if self.oms_core is None:
                logger.error("OMS core not initialized - cannot perform reconciliation")
                return []

            oms_store = self.oms_core.get_store()
            venue_adapter = self.execution_router.get_adapter()

            # Create reconciliation service for initial reconciliation
            from polytrader.oms.reconcile import ReconciliationService

            reconciliation_service = ReconciliationService(
                store=oms_store,
                venue_adapter=venue_adapter,
                bus=self.bus,
            )

            # Run initial reconciliation
            divergences = await reconciliation_service.reconcile()

            # Check for severe divergences (ERROR severity)
            severe_divergences = [d for d in divergences if d.severity == "ERROR"]

            if severe_divergences:
                logger.error(
                    "Initial reconciliation detected {count} severe divergence(s)",
                    count=len(severe_divergences),
                    divergences=[d.model_dump() for d in severe_divergences],
                )
            elif divergences:
                logger.warning(
                    "Initial reconciliation detected {count} divergence(s) (non-severe)",
                    count=len(divergences),
                )
            else:
                logger.info("Initial reconciliation complete: no divergences detected")

            # Store reconciliation service for periodic reconciliation later
            self._reconciliation_service = reconciliation_service

            return divergences

        except Exception as e:
            logger.exception(
                "Error during initial reconciliation: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue with startup even if reconciliation fails
            # (health gates will fail if reconciliation is required)
            return []

    async def _evaluate_health_gates(
        self, initial_reconciliation_divergences: list[Any]
    ) -> "HealthStatus | None":
        """Evaluate health gates.

        Per flows.mdc §2: Health gates (market data freshness, user stream, reconciliation, etc.).

        Args:
            initial_reconciliation_divergences: Divergences from initial reconciliation

        Returns:
            HealthStatus if evaluated, None if skipped (paper trading mode)
        """
        # Only for live trading (paper trading doesn't need this)
        if not (
            self.health_service_factory is not None
            or (
                self.execution_router_factory is not None
                and self.user_stream_adapter_factory is not None
            )
        ):
            # Paper trading mode - health gates not required
            logger.debug("Health gates skipped (paper trading mode)")
            self._health_gates_passed = True
            return None

        logger.info("Evaluating health gates")
        self._health_gates_passed = True

        try:
            # Create user stream adapter early if needed for health check
            # (it will be started as a service later)
            # Note: User stream adapter may not be connected yet at this point,
            # so we create it but don't require connection for initial health gates
            user_stream_adapter_for_health = None
            if self.user_stream_adapter_factory is not None:
                user_stream_adapter_for_health = self.user_stream_adapter_factory()
                self._user_stream_adapter = user_stream_adapter_for_health

            # Create health service if factory provided, otherwise create default
            if self.health_service_factory is not None:
                health_service = self.health_service_factory()
            else:
                # Create default health service with available components
                # Note: For initial health gates, user stream may not be connected yet,
                # so we use thresholds that don't require user stream for initial boot
                initial_thresholds = HealthGateThresholds(
                    max_market_data_staleness_seconds=(
                        self.health_gate_thresholds.max_market_data_staleness_seconds
                    ),
                    max_reconciliation_divergences=(
                        self.health_gate_thresholds.max_reconciliation_divergences
                    ),
                    max_error_rate=self.health_gate_thresholds.max_error_rate,
                    require_user_stream=False,  # Don't require user stream for initial boot
                )
                health_service = HealthService(
                    store=self.store,
                    thresholds=initial_thresholds,
                    user_stream_adapter=user_stream_adapter_for_health,
                    circuit_breaker=self._circuit_breaker,
                    execution_control=self._execution_control,
                    kill_switch_active=False,  # Kill switch not active on boot
                    error_rate=None,  # Error rate not tracked on boot
                    recent_reconcile_events=initial_reconciliation_divergences,
                )

            # Evaluate health status
            health_status = await health_service.evaluate()

            # Check all gates
            all_passed, failed_gates = health_service.check_gates(health_status)

            if all_passed:
                logger.info(
                    "All health gates passed",
                    market_data_fresh=health_status.market_data_fresh,
                    user_stream_connected=health_status.user_stream_connected,
                    reconciliation_healthy=health_status.reconciliation_healthy,
                    error_rate_ok=health_status.error_rate_ok,
                    circuit_breaker_triggered=health_status.circuit_breaker_triggered,
                    kill_switch_active=health_status.kill_switch_active,
                )
                self._health_gates_passed = True
            else:
                logger.error(
                    "Health gates failed: {gates}",
                    gates=", ".join(failed_gates),
                    market_data_fresh=health_status.market_data_fresh,
                    market_data_staleness_seconds=health_status.market_data_staleness_seconds,
                    user_stream_connected=health_status.user_stream_connected,
                    reconciliation_healthy=health_status.reconciliation_healthy,
                    reconciliation_divergence_count=(health_status.reconciliation_divergence_count),
                    error_rate_ok=health_status.error_rate_ok,
                    error_rate=health_status.error_rate,
                    circuit_breaker_triggered=health_status.circuit_breaker_triggered,
                    kill_switch_active=health_status.kill_switch_active,
                )
                self._health_gates_passed = False

            return health_status

        except Exception as e:
            logger.exception(
                "Error during health gate evaluation: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Fail health gates if evaluation fails
            self._health_gates_passed = False
            return None

    async def _issue_execution_permit(self, health_status: "HealthStatus | None") -> None:
        """Issue execution permit.

        Per flows.mdc §2: Issue execution permit only if all health gates pass.

        Args:
            health_status: Health status from health gate evaluation (None if skipped)
        """
        if self._execution_control is None:
            logger.debug("Execution permit skipped (no execution control)")
            return

        if not self._health_gates_passed:
            logger.error("Health gates failed, execution permit NOT issued")
            return

        logger.info("Issuing execution permit (all health gates passed)")
        try:
            # Convert health_status to dict for permit event (if available)
            health_status_dict: dict[str, Any] = {}
            if health_status is not None:
                health_status_dict = {
                    "market_data_fresh": health_status.market_data_fresh,
                    "market_data_staleness_seconds": (health_status.market_data_staleness_seconds),
                    "user_stream_connected": health_status.user_stream_connected,
                    "reconciliation_healthy": health_status.reconciliation_healthy,
                    "reconciliation_divergence_count": (
                        health_status.reconciliation_divergence_count
                    ),
                    "error_rate_ok": health_status.error_rate_ok,
                    "error_rate": health_status.error_rate,
                    "circuit_breaker_triggered": health_status.circuit_breaker_triggered,
                    "kill_switch_active": health_status.kill_switch_active,
                }

            # Issue execution permit
            await self._execution_control.enable_with_permit(
                permit_type="boot",
                reason="All health gates passed during boot sequence",
                health_status=health_status_dict,
                issued_by="system",
            )
            logger.info("Execution permit issued successfully")
        except Exception as e:
            logger.exception(
                "Error issuing execution permit: {error}",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't fail boot if permit issuance fails, but execution will remain disabled

    async def _start_services(self) -> int:
        """Start all services in correct order.

        Order: PortfolioService → RiskChecker → OMS Core → ExecutionRouter → PositionManager
        (Subscribers before publishers)

        Returns:
            Number of services started
        """
        services_started = 0

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
        # Per review: OMS core already created early in boot sequence, reuse it
        if self.oms_core is None:
            logger.error("OMS core not initialized - cannot start service")
        else:
            oms_core = self.oms_core
            await self._start_service_task(
                "OMSCore",
                oms_core,
                lambda: oms_core.run(),
                lambda task: setattr(self, "_oms_core_task", task),
            )
            services_started += 1

        # 4. ExecutionRouter subscribes to SUBMIT_ORDER_COMMANDS (if enabled)
        # Per review: Execution router already created early in boot sequence, reuse it
        if self.execution_router_factory is not None:
            if self.execution_router is None:
                logger.error("Execution router not initialized - cannot start service")
            else:
                execution_router = self.execution_router
                await self._start_service_task(
                    "ExecutionRouter",
                    execution_router,
                    lambda: execution_router.run(),
                    lambda task: setattr(self, "_execution_router_task", task),
                )
                services_started += 1

        # 5. PositionManager (background sync)
        # Per review: Position manager already created early in boot sequence, reuse it
        if self.position_manager_factory is not None:
            if self.position_manager is None:
                logger.error("Position manager not initialized - cannot start service")
            else:
                position_manager = self.position_manager
                await self._start_service_task(
                    "PositionManager",
                    position_manager,
                    lambda: position_manager.run(),
                    lambda task: setattr(self, "_position_manager_task", task),
                )
                services_started += 1

        # 6. UserStreamAdapter (for live trading, after OMS Core)
        # Note: User stream adapter may have been created earlier for health gate evaluation
        if self.user_stream_adapter_factory is not None:
            if self._user_stream_adapter is None:
                user_stream_adapter = self.user_stream_adapter_factory()
                self._user_stream_adapter = user_stream_adapter
            else:
                user_stream_adapter = self._user_stream_adapter
            await self._start_service_task(
                "UserStreamAdapter",
                user_stream_adapter,
                lambda: user_stream_adapter.run(),
                lambda task: setattr(self, "_user_stream_task", task),
            )
            services_started += 1

        # 7. ReconciliationService (for live trading, after OMS Core and ExecutionRouter)
        # (Already created above for initial reconciliation, just start periodic task now)
        if self._reconciliation_service is not None:
            reconciliation_service = self._reconciliation_service
            await self._start_reconciliation_task(reconciliation_service)
            services_started += 1
        elif self.reconciliation_service_factory is not None:
            # Fallback: create reconciliation service if not already created
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

        # 9. EventSink (mandatory, per proposal)
        if self._event_sink is not None:
            await self._start_event_sink_task()
            services_started += 1
        else:
            logger.warning("EventSink not initialized - events will not be persisted to database")

        # 10. ControlPlaneService (optional, runtime commands)
        if self._control_plane is not None:
            await self._start_service_task(
                "ControlPlaneService",
                self._control_plane,
                lambda: self._control_plane.run(),
                lambda task: setattr(self, "_control_plane_task", task),
            )
            services_started += 1

        return services_started

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

    async def _start_event_sink_task(self) -> None:
        """Start EventSink as a separate async task.

        Per proposal: EventSink runs independently and handles errors gracefully.
        """
        if self._event_sink is None:
            return

        service_start = time.perf_counter()

        try:
            # Start EventSink task
            task = asyncio.create_task(self._event_sink.run())
            self._event_sink_task = task

            # Wait a short time for EventSink to initialize
            await asyncio.sleep(self.startup_delay_s)

            # Record metrics and emit event
            startup_time_ms = (time.perf_counter() - service_start) * 1000
            record_service_started("EventSink", SUPERVISOR_TYPE, startup_time_ms)

            started_event = ServiceStartedEvent(
                service_name="EventSink",
                supervisor_type=SUPERVISOR_TYPE,
                startup_time_ms=startup_time_ms,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, started_event)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service="EventSink",
                startup_time_ms=startup_time_ms,
            ).debug(
                "EventSink started in {time_ms:.1f}ms",
                time_ms=startup_time_ms,
            )

        except Exception as e:
            error_class = classify_service_error(e)
            error_type = type(e).__name__
            error_msg = str(e)

            logger.bind(
                supervisor=SUPERVISOR_TYPE,
                service="EventSink",
                error_type=error_type,
                error_class=error_class,
            ).exception(
                "Failed to start EventSink: {error}. "
                "System will continue without event persistence.",
                error=error_msg,
            )

            # Emit error event
            error_event = ServiceErrorEvent(
                service_name="EventSink",
                supervisor_type=SUPERVISOR_TYPE,
                error_type=error_type,
                error_message=error_msg,
                error_class=error_class,
            )
            await self.bus.publish(SYSTEM_LIFECYCLE, error_event)

            # Record metric
            record_service_error("EventSink", SUPERVISOR_TYPE, error_type, error_class)

            # Don't re-raise - EventSink failures should not prevent system startup
            # (per proposal: graceful error handling)

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
        # Stop ControlPlaneService
        if self._control_plane is not None:
            try:
                self._control_plane.stop()
                record_service_stopped("ControlPlaneService", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="ControlPlaneService",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="ControlPlaneService").debug(
                    "ControlPlaneService stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="ControlPlaneService",
                    error_type=type(e).__name__,
                ).exception("Error stopping ControlPlaneService: {error}", error=str(e))
            finally:
                if self._control_plane_task is not None:
                    if not self._control_plane_task.done():
                        self._control_plane_task.cancel()
                    try:
                        await asyncio.wait_for(self._control_plane_task, timeout=5.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    self._control_plane_task = None
                self._control_plane = None

        # Stop EventSink (should be last to flush remaining events)
        if self._event_sink is not None:
            try:
                await self._event_sink.stop()
                record_service_stopped("EventSink", SUPERVISOR_TYPE)
                stopped_event = ServiceStoppedEvent(
                    service_name="EventSink",
                    supervisor_type=SUPERVISOR_TYPE,
                    reason=None,
                )
                await self.bus.publish(SYSTEM_LIFECYCLE, stopped_event)
                logger.bind(supervisor=SUPERVISOR_TYPE, service="EventSink").debug(
                    "EventSink stopped"
                )
                services_stopped += 1
            except Exception as e:
                logger.bind(
                    supervisor=SUPERVISOR_TYPE,
                    service="EventSink",
                    error_type=type(e).__name__,
                ).exception("Error stopping EventSink: {error}", error=str(e))
            finally:
                if self._event_sink_task is not None:
                    if not self._event_sink_task.done():
                        self._event_sink_task.cancel()
                    try:
                        await asyncio.wait_for(self._event_sink_task, timeout=5.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    self._event_sink_task = None
                # Cleanup event store
                if hasattr(self._event_sink, "_store"):
                    try:
                        await self._event_sink._store.cleanup()
                    except Exception as cleanup_error:
                        logger.exception(
                            "Error cleaning up EventSink store: {error}",
                            error=str(cleanup_error),
                        )
                self._event_sink = None

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
            self._event_sink_task,
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
        self._event_sink_task = None
        self._control_plane_task = None

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
                    self._event_sink_task,
                    self._control_plane_task,
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
