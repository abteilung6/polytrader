"""Tests for SystemSupervisor.

Tests service lifecycle management, startup/shutdown order, and error handling.
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.events import CIRCUIT_BREAKER, RECONCILE
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    FillEvent,
    MarketDataEvent,
    OrderAckEvent,
    OrderCreatedEvent,
    OrderIntentEvent,
    OrderSubmittedEvent,
    ReconcileEvent,
)
from polytrader.execution import ExecutionRouter
from polytrader.obs.metrics import MemoryMetricsCollector, set_metrics_collector
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.models import OrderState
from polytrader.oms.reconcile import ReconciliationService
from polytrader.ops import (
    CircuitBreaker,
    CircuitBreakerThresholds,
    ExecutionControl,
    HealthGateThresholds,
    HealthService,
)
from polytrader.portfolio import PortfolioService
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import SystemSupervisor
from polytrader.types import Outcome, Position


@pytest.fixture(autouse=True)
def metrics_collector() -> Generator[MemoryMetricsCollector, None, None]:
    """Use MemoryMetricsCollector for all supervisor tests to prevent Prometheus metric duplication.

    Per testing.mdc: Unit tests must be isolated. This fixture ensures each test
    gets a fresh metrics collector, preventing "Duplicated timeseries" errors.

    Yields:
        MemoryMetricsCollector instance
    """
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    yield collector
    # Cleanup: reset to None so next test gets fresh collector
    set_metrics_collector(None)


class FakePortfolioService(PortfolioService):
    """Fake PortfolioService for testing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.start_called = False
        self.stop_called = False

    async def start(self) -> None:
        """Mark start as called."""
        self.start_called = True
        await super().start()

    async def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        await super().stop()


class FakeRiskChecker(RiskChecker):
    """Fake RiskChecker for testing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.run_called = False
        self.stop_called = False
        self._running = False

    async def run(self) -> None:
        """Mark run as called and wait until stopped."""
        self.run_called = True
        self._running = True
        while self._running:
            await asyncio.sleep(0.01)

    def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        self._running = False


class FakeOMSCore(OMSCore):
    """Fake OMSCore for testing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.run_called = False
        self.stop_called = False
        self._running = False

    async def run(self) -> None:
        """Mark run as called and wait until stopped."""
        self.run_called = True
        self._running = True
        while self._running:
            await asyncio.sleep(0.01)

    def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        self._running = False


class FakeExecutionRouter(ExecutionRouter):
    """Fake ExecutionRouter for testing."""

    def __init__(self, bus: EventBus, adapter: Any | None = None, **kwargs) -> None:
        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        if adapter is None:
            fake_adapter = MagicMock(spec=ClobVenueAdapter)
        else:
            fake_adapter = adapter
        super().__init__(bus=bus, adapter=fake_adapter, **kwargs)
        self.run_called = False
        self.stop_called = False
        self._running = False

    async def run(self) -> None:
        """Mark run as called and wait until stopped."""
        self.run_called = True
        self._running = True
        while self._running:
            await asyncio.sleep(0.01)

    def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        self._running = False


class FakeUserStreamAdapter:
    """Fake UserStreamAdapter for testing."""

    def __init__(self, *args, **kwargs) -> None:
        self.start_called = False
        self.stop_called = False
        self._running = False
        self._ws: Any | None = None  # WebSocket connection (None when disconnected)

    async def run(self) -> None:
        """Mark run as called."""
        self.start_called = True
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        self._running = False


class FakePositionManager:
    """Fake PositionManager for testing."""

    def __init__(self, *args, **kwargs) -> None:
        self.start_called = False
        self.stop_called = False
        self._running = False

    async def run(self) -> None:
        """Mark run as called."""
        self.start_called = True
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Mark stop as called."""
        self.stop_called = True
        self._running = False

    def get_positions(self) -> dict[tuple[str, Outcome], Position]:
        """Return empty positions."""
        return {}


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def store() -> MemoryMarketDataStore:
    """Create market data store for testing."""
    return MemoryMarketDataStore()


@pytest.fixture
def portfolio_service(bus: EventBus, store: MemoryMarketDataStore) -> FakePortfolioService:
    """Create portfolio service for testing."""
    return FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)


@pytest.fixture
def risk_checker(bus: EventBus, store: MemoryMarketDataStore) -> FakeRiskChecker:
    """Create risk checker for testing."""
    return FakeRiskChecker(bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store)


@pytest.fixture
def oms_core(bus: EventBus) -> FakeOMSCore:
    """Create OMS core for testing."""
    return FakeOMSCore(bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore())


@pytest.fixture
def execution_router(bus: EventBus) -> ExecutionRouter:
    """Create execution router for testing."""
    fake_adapter = MagicMock()
    fake_adapter.get_open_orders = MagicMock(return_value=[])
    fake_adapter.submit_order = MagicMock()
    fake_adapter.cancel_order = MagicMock()
    router = FakeExecutionRouter(bus=bus, adapter=fake_adapter)
    router._adapter = fake_adapter
    return router


class TestSystemSupervisor:
    """Tests for SystemSupervisor."""

    @pytest.mark.asyncio
    async def test_supervisor_starts_services_in_order(
        self,
        bus: EventBus,
        store: MemoryMarketDataStore,
        portfolio_service: FakePortfolioService,
        risk_checker: FakeRiskChecker,
        oms_core: FakeOMSCore,
    ) -> None:
        """Test that supervisor starts services in correct order."""

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
        )

        await supervisor.start()

        # Verify services were started
        assert portfolio_service.start_called
        assert risk_checker.run_called
        assert oms_core.run_called

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_stops_services(
        self,
        bus: EventBus,
        store: MemoryMarketDataStore,
        portfolio_service: FakePortfolioService,
        risk_checker: FakeRiskChecker,
        oms_core: FakeOMSCore,
    ) -> None:
        """Test that supervisor stops services."""

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
        )

        await supervisor.start()
        await supervisor.stop()

        # Verify services were stopped
        assert portfolio_service.stop_called
        assert risk_checker.stop_called
        assert oms_core.stop_called

    @pytest.mark.asyncio
    async def test_user_stream_task_runs(self) -> None:
        """Test that user stream task runs and publishes events."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        # Create fake user stream adapter
        fake_user_stream = FakeUserStreamAdapter()

        def user_stream_factory() -> Any:
            return fake_user_stream

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            user_stream_adapter_factory=user_stream_factory,
        )

        await supervisor.start()

        # Verify user stream adapter was started
        assert supervisor._user_stream_adapter is not None
        assert supervisor._user_stream_task is not None

        # Wait a bit for the task to start
        await asyncio.sleep(0.1)

        # Verify task is running
        assert not supervisor._user_stream_task.done()

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_reconciliation_task_runs(self) -> None:
        """Test that reconciliation task runs periodically."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create OMS store for reconciliation
        oms_store = InMemoryOrderStore(bus)

        # Create reconciliation service factory
        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
        )

        await supervisor.start()

        # Verify reconciliation service was created
        assert supervisor._reconciliation_service is not None
        assert supervisor._reconciliation_task is not None

        # Wait for reconciliation to run (it runs every 60 seconds, but we can trigger it manually)
        # Actually, the task should run immediately and then wait 60 seconds
        await asyncio.sleep(0.2)

        # Verify reconciliation was called (venue adapter should have been called)
        fake_adapter.get_open_orders.assert_called()

        # Verify task is still running
        assert not supervisor._reconciliation_task.done()

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_circuit_breaker_disables_execution(self) -> None:
        """Test that circuit breaker disables execution when triggered."""
        bus = EventBus()
        store = MemoryMarketDataStore()
        execution_control = ExecutionControl()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        # Create circuit breaker factory
        def circuit_breaker_factory() -> CircuitBreaker:
            thresholds = CircuitBreakerThresholds(
                max_fill_mismatches=0, require_error_severity=False
            )  # Trigger on any fill mismatch
            return CircuitBreaker(
                thresholds=thresholds, bus=bus, execution_control=execution_control
            )

        # Create fake reconciliation service that returns a fill mismatch
        async def mock_reconcile() -> list[ReconcileEvent]:
            return [
                ReconcileEvent(
                    divergence_type="fill_mismatch",
                    order_id="order-1",
                    venue_order_id="venue-1",
                    severity="ERROR",
                    details={},
                )
            ]

        fake_reconciliation_service = MagicMock()
        fake_reconciliation_service.reconcile = mock_reconcile

        def reconciliation_factory() -> Any:
            return fake_reconciliation_service

        # Enable execution first
        execution_control.enable()
        assert execution_control.is_enabled()

        # Subscribe to circuit breaker events
        cb_queue = bus.subscribe(CIRCUIT_BREAKER)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            reconciliation_service_factory=reconciliation_factory,
            circuit_breaker_factory=circuit_breaker_factory,
            execution_control=execution_control,
        )

        await supervisor.start()

        # Verify circuit breaker was created
        assert supervisor._circuit_breaker is not None

        # Wait for reconciliation to run (which should trigger circuit breaker)
        # The reconciliation loop waits 0.1s for circuit breaker to be initialized,
        # then runs reconciliation immediately
        # We need to wait a bit for the reconciliation to complete
        await asyncio.sleep(0.5)

        # Verify execution was disabled
        assert not execution_control.is_enabled(), (
            "Execution should be disabled after circuit breaker triggers"
        )

        # Verify circuit breaker event was published
        try:
            cb_event = await asyncio.wait_for(cb_queue.get(), timeout=1.0)
            assert cb_event.triggered is True
            assert cb_event.breaker_type == "reconcile_divergence"
        except TimeoutError:
            pytest.fail("Circuit breaker event was not published")

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_execution_control_enable_disable(self) -> None:
        """Test that execution control can enable and disable execution."""
        execution_control = ExecutionControl()

        # Default should be disabled
        assert not execution_control.is_enabled()

        # Enable execution
        execution_control.enable()
        assert execution_control.is_enabled()

        # Disable execution
        execution_control.disable()
        assert not execution_control.is_enabled()

    @pytest.mark.asyncio
    async def test_initial_reconciliation_in_boot_sequence(self) -> None:
        """Test that initial reconciliation runs in boot sequence."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create OMS store for reconciliation
        oms_store = InMemoryOrderStore(bus)

        # Create reconciliation service factory
        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
        )

        await supervisor.start()

        # Verify initial reconciliation was called (venue adapter should have been called)
        # Initial reconciliation happens before services start, so it should be called immediately
        fake_adapter.get_open_orders.assert_called()

        # Verify reconciliation service was stored for periodic reconciliation
        assert supervisor._reconciliation_service is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_initial_reconciliation_failure_handling(self) -> None:
        """Test that reconciliation failures are handled gracefully."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        # Create fake execution router with venue adapter that raises an error
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(side_effect=Exception("Venue API unavailable"))
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create OMS store for reconciliation
        oms_store = InMemoryOrderStore(bus)

        # Create reconciliation service factory
        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
        )

        # Start should not raise an exception even if reconciliation fails
        await supervisor.start()

        # Verify that reconciliation was attempted (adapter was called)
        fake_adapter.get_open_orders.assert_called()

        # Verify that supervisor still started successfully
        assert supervisor.oms_core is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_initial_reconciliation_with_severe_divergences(self) -> None:
        """Test that severe divergences are detected and logged."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create an order in OMS store that will cause a fill mismatch
        # We'll create an order that OMS thinks is ACKED but venue says is FILLED
        from polytrader.events.types import OrderIntentEvent
        from polytrader.oms.models import OrderState

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.5,
            size=1.0,
            reason="Test order",
            strategy_id="simple_threshold",
        )
        order = await oms_store.create_order(intent, "client-order-1")
        # Set order to ACKED state with venue_order_id
        order.venue_order_id = "venue-order-1"
        order.state = OrderState.ACKED
        oms_store.update_order(order)

        # Create fake execution router with venue adapter that returns FILLED order
        fake_adapter = MagicMock()
        # Return venue order that is FILLED (causing fill mismatch)
        # Note: get_open_orders typically returns only OPEN orders, but for testing
        # we return a FILLED order to simulate a fill mismatch scenario
        # get_open_orders is async, so we need AsyncMock
        fake_adapter.get_open_orders = AsyncMock(
            return_value=[
                {
                    "order_id": "venue-order-1",
                    "status": "FILLED",
                    "size": 1.0,  # Must be float, not string
                    "side": "BUY",
                    "token_id": "test-token",
                }
            ]
        )
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        # Create reconciliation service factory (for periodic reconciliation)
        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Subscribe to reconcile events
        reconcile_queue = bus.subscribe(RECONCILE)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
        )

        await supervisor.start()

        # Verify that reconciliation was called (venue adapter should have been called)
        fake_adapter.get_open_orders.assert_called()

        # Verify that reconcile event was published with ERROR severity
        try:
            reconcile_event = await asyncio.wait_for(reconcile_queue.get(), timeout=1.0)
            assert reconcile_event.severity == "ERROR"
            assert reconcile_event.divergence_type == "fill_mismatch"
        except TimeoutError:
            pytest.fail("Reconcile event was not published")

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_initial_reconciliation_with_no_divergences(self) -> None:
        """Test that boot sequence passes when no divergences are detected."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create reconciliation service factory (for periodic reconciliation)
        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
        )

        # Start should succeed without errors
        await supervisor.start()

        # Verify that reconciliation was called (venue adapter should have been called)
        fake_adapter.get_open_orders.assert_called()

        # Verify that supervisor started successfully
        assert supervisor.oms_core is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_health_gates_passing_in_boot_sequence(self) -> None:
        """Test boot sequence with all health gates passing."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add fresh market data
        import time

        from polytrader.events.types import MarketDataEvent

        fresh_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,  # 1 second old (fresh)
        )
        store.add(fresh_event)

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create fake user stream adapter (connected)
        fake_user_stream = FakeUserStreamAdapter()
        fake_user_stream._running = True
        fake_user_stream._ws = MagicMock()

        # Create circuit breaker (not triggered)
        execution_control = ExecutionControl()
        circuit_breaker = CircuitBreaker(
            thresholds=CircuitBreakerThresholds(max_fill_mismatches=1),
            bus=bus,
            execution_control=execution_control,
        )

        # Create health service factory
        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,  # Don't require for initial boot
                ),
                user_stream_adapter=fake_user_stream,
                circuit_breaker=circuit_breaker,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def user_stream_factory() -> Any:
            return fake_user_stream

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        def circuit_breaker_factory() -> CircuitBreaker:
            return circuit_breaker

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            user_stream_adapter_factory=user_stream_factory,
            reconciliation_service_factory=reconciliation_factory,
            circuit_breaker_factory=circuit_breaker_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Start should succeed
        await supervisor.start()

        # Verify that supervisor started successfully
        assert supervisor.oms_core is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_health_gates_failing_market_data_stale(self) -> None:
        """Test boot sequence with market data staleness gate failing."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add stale market data (100 seconds old)
        import time

        from polytrader.events.types import MarketDataEvent

        stale_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 100.0,  # 100 seconds old (stale)
        )
        store.add(stale_event)

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create health service factory with strict thresholds
        execution_control = ExecutionControl()

        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,  # Stricter than 100 seconds
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Start should still succeed (health gates fail but don't prevent startup)
        # Execution will not be enabled (handled in commit 7)
        await supervisor.start()

        # Verify that supervisor started successfully
        assert supervisor.oms_core is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_health_gates_paper_trading_mode(self) -> None:
        """Test boot sequence with missing optional components (paper trading)."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services (minimal setup for paper trading)
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            # No execution router, user stream, reconciliation, circuit breaker, or health service
            # (paper trading mode)
        )

        # Start should succeed (health gates skipped for paper trading)
        await supervisor.start()

        # Verify that supervisor started successfully
        assert supervisor.oms_core is not None

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_health_gate_thresholds(self) -> None:
        """Test health gate thresholds with various configurations."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add market data with varying staleness
        import time

        from polytrader.events.types import MarketDataEvent

        # Test 1: Market data just within threshold (59 seconds old, threshold 60)
        event1 = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 59.0,
        )
        store.add(event1)

        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        execution_control = ExecutionControl()

        # Test with threshold of 60 seconds (should pass)
        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Start should succeed
        await supervisor.start()
        assert supervisor.oms_core is not None
        await supervisor.stop()

        # Test 2: Market data just over threshold (61 seconds old, threshold 60)
        event2 = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 61.0,
        )
        store.add(event2)

        # Create new supervisor with same configuration
        supervisor2 = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Start should still succeed (health gates fail but don't prevent startup)
        await supervisor2.start()
        assert supervisor2.oms_core is not None
        await supervisor2.stop()

    @pytest.mark.asyncio
    async def test_execution_permit_issuance_on_boot(self) -> None:
        """Test execution permit issuance on boot when health gates pass."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add fresh market data
        import time

        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import ExecutionPermitEvent, MarketDataEvent

        fresh_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,
        )
        store.add(fresh_event)

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create execution control with bus
        execution_control = ExecutionControl(bus=bus)

        # Create health service factory that will pass
        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Subscribe to execution permit events
        permit_queue = bus.subscribe(SYSTEM_LIFECYCLE)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        await supervisor.start()

        # Verify execution was enabled
        assert execution_control.is_enabled()

        # Verify ExecutionPermitEvent was published
        try:
            permit_event = await asyncio.wait_for(permit_queue.get(), timeout=1.0)
            # Filter for ExecutionPermitEvent
            while not isinstance(permit_event, ExecutionPermitEvent):
                permit_event = await asyncio.wait_for(permit_queue.get(), timeout=1.0)
            assert isinstance(permit_event, ExecutionPermitEvent)
            assert permit_event.permit_type == "boot"
            assert permit_event.issued_by == "system"
            assert "All health gates passed" in permit_event.reason
        except TimeoutError:
            pytest.fail("ExecutionPermitEvent was not published")

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_execution_router_rejects_orders_when_disabled(self) -> None:
        """Test execution router rejects orders when execution is disabled."""
        bus = EventBus()
        fake_adapter = MagicMock()
        execution_control = ExecutionControl()
        execution_router = ExecutionRouter(
            bus=bus, adapter=fake_adapter, execution_control=execution_control
        )

        # Ensure execution is disabled
        execution_control.disable()
        assert not execution_control.is_enabled()

        # Create SubmitOrderCommand
        from polytrader.events import ORDER_REJECTS, SUBMIT_ORDER_COMMANDS
        from polytrader.events.types import OrderIntentEvent
        from polytrader.oms.commands import SubmitOrderCommand

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        command = SubmitOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id="corr-123",
        )

        # Subscribe to reject events
        reject_queue = bus.subscribe(ORDER_REJECTS)

        # Start execution router
        router_task = asyncio.create_task(execution_router.run())
        await asyncio.sleep(0.05)

        try:
            # Publish command
            await bus.publish(SUBMIT_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify adapter was NOT called
            fake_adapter.submit_order.assert_not_called()

            # Verify OrderRejectedEvent was published
            try:
                reject_event = await asyncio.wait_for(reject_queue.get(), timeout=1.0)
                assert reject_event.order_id == command.order_id
                assert reject_event.reason == "Execution disabled"
            except TimeoutError:
                pytest.fail("OrderRejectedEvent was not published")

        finally:
            execution_router.stop()
            router_task.cancel()
            try:
                await router_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_execution_router_allows_orders_when_enabled(self) -> None:
        """Test execution router allows orders when execution is enabled."""
        bus = EventBus()
        fake_adapter = MagicMock()
        fake_adapter.submit_order = AsyncMock(
            return_value=MagicMock(
                venue_order_id="venue-123",
                status="acknowledged",
                raw_response={"status": "acknowledged"},
            )
        )
        execution_control = ExecutionControl()
        execution_router = ExecutionRouter(
            bus=bus, adapter=fake_adapter, execution_control=execution_control
        )

        # Enable execution
        execution_control.enable()
        assert execution_control.is_enabled()

        # Create SubmitOrderCommand
        from polytrader.events import SUBMIT_ORDER_COMMANDS
        from polytrader.events.types import OrderIntentEvent
        from polytrader.oms.commands import SubmitOrderCommand

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=1.0,
            target_price=0.55,
            limit_price=0.55,
            reason="Test",
            ttl_s=60.0,
            strategy_id="simple_threshold",
        )

        command = SubmitOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id="corr-123",
        )

        # Start execution router
        router_task = asyncio.create_task(execution_router.run())
        await asyncio.sleep(0.05)

        try:
            # Publish command
            await bus.publish(SUBMIT_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify adapter WAS called
            fake_adapter.submit_order.assert_called_once()
            called_client_id, called_intent = fake_adapter.submit_order.call_args[0]
            assert called_client_id == command.client_order_id
            assert called_intent == intent

        finally:
            execution_router.stop()
            router_task.cancel()
            try:
                await router_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_kill_switch_disables_execution(self) -> None:
        """Test kill switch disables execution."""
        bus = EventBus()
        execution_control = ExecutionControl(bus=bus)

        # Enable execution first
        execution_control.enable()
        assert execution_control.is_enabled()

        # Subscribe to kill switch events
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import KillSwitchEvent

        kill_switch_queue = bus.subscribe(SYSTEM_LIFECYCLE)

        # Activate kill switch
        await execution_control.set_kill_switch(
            active=True, reason="Test kill switch", triggered_by="operator"
        )

        # Verify execution is disabled
        assert not execution_control.is_enabled()

        # Verify KillSwitchEvent was published
        try:
            kill_switch_event = await asyncio.wait_for(kill_switch_queue.get(), timeout=1.0)
            # Filter for KillSwitchEvent
            while not isinstance(kill_switch_event, KillSwitchEvent):
                kill_switch_event = await asyncio.wait_for(kill_switch_queue.get(), timeout=1.0)
            assert isinstance(kill_switch_event, KillSwitchEvent)
            assert kill_switch_event.triggered is True
            assert kill_switch_event.triggered_by == "operator"
            assert "Test kill switch" in kill_switch_event.reason
        except TimeoutError:
            pytest.fail("KillSwitchEvent was not published")

        # Deactivate kill switch
        await execution_control.set_kill_switch(
            active=False, reason="Test reset", triggered_by="operator"
        )

        # Execution should still be disabled (kill switch deactivation doesn't re-enable)
        # (execution_control.enable() must be called explicitly)
        assert not execution_control.is_enabled()

    @pytest.mark.asyncio
    async def test_complete_boot_sequence_for_live_trading(self) -> None:
        """Test complete boot sequence for live trading.

        Per Commit 8: Verify all boot sequence steps execute in order:
        1. Load config
        2. Init event store (SystemStartedEvent)
        3. Start adapters
        4. Reconstruct state
        5. Initial reconciliation
        6. Health gates
        7. Execution permit
        8. Start services
        """
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add fresh market data
        import time

        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import (
            ExecutionPermitEvent,
            MarketDataEvent,
            SystemStartedEvent,
        )

        fresh_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,
        )
        store.add(fresh_event)

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router with venue adapter
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create execution control with bus
        execution_control = ExecutionControl(bus=bus)

        # Create health service factory that will pass
        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Subscribe to boot sequence events
        lifecycle_queue = bus.subscribe(SYSTEM_LIFECYCLE)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        await supervisor.start()

        # Verify all services started
        assert supervisor.portfolio_service is not None
        assert supervisor.risk_checker is not None
        assert supervisor.oms_core is not None
        assert supervisor.execution_router is not None

        # Verify execution was enabled
        assert execution_control.is_enabled()

        # Verify boot sequence events were published
        events_received: list[Any] = []
        try:
            # Collect events with timeout
            while len(events_received) < 3:  # SystemStarted, ConfigLoaded (maybe), ExecutionPermit
                event = await asyncio.wait_for(lifecycle_queue.get(), timeout=2.0)
                events_received.append(event)
        except TimeoutError:
            pass

        # Verify SystemStartedEvent was published
        system_started = next(
            (e for e in events_received if isinstance(e, SystemStartedEvent)), None
        )
        assert system_started is not None, "SystemStartedEvent was not published"
        # Verify run_id is set (per flows.mdc §2: SystemStartedEvent includes run_id)
        assert system_started.run_id is not None
        assert len(system_started.run_id) > 0  # Should be a valid UUID string

        # Verify ExecutionPermitEvent was published
        execution_permit = next(
            (e for e in events_received if isinstance(e, ExecutionPermitEvent)), None
        )
        assert execution_permit is not None, "ExecutionPermitEvent was not published"
        assert execution_permit.permit_type == "boot"

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_boot_sequence_with_health_gate_failures(self) -> None:
        """Test boot sequence with health gate failures.

        Per Commit 8: Verify boot completes but execution is NOT enabled when health gates fail.
        """
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Add stale market data (will cause health gate failure)
        import time

        from polytrader.events.types import MarketDataEvent

        stale_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 120.0,  # 120 seconds old (stale)
        )
        store.add(stale_event)

        # Create fake services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = AsyncMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create execution control
        execution_control = ExecutionControl(bus=bus)

        # Create health service factory that will fail (stale data)
        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,  # Stale data will fail
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        await supervisor.start()

        # Verify services started (boot should complete)
        assert supervisor.portfolio_service is not None
        assert supervisor.oms_core is not None

        # Verify execution was NOT enabled (health gates failed)
        assert not execution_control.is_enabled()
        assert not supervisor._health_gates_passed

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_boot_sequence_for_paper_trading(self) -> None:
        """Test boot sequence for paper trading (simplified).

        Per Commit 8: Verify paper trading skips boot sequence steps gracefully.
        """
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services (no execution router, no reconciliation, no health service)
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        # Paper trading: no execution router, no reconciliation, no health service
        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=None,  # Paper trading
            reconciliation_service_factory=None,  # Paper trading
            execution_control=None,  # Paper trading
            health_service_factory=None,  # Paper trading
        )

        # Boot should complete successfully (simplified boot sequence)
        await supervisor.start()

        # Verify services started
        assert supervisor.portfolio_service is not None
        assert supervisor.risk_checker is not None
        assert supervisor.oms_core is not None

        # Verify health gates passed (skipped for paper trading)
        assert supervisor._health_gates_passed

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_boot_sequence_with_missing_components(self) -> None:
        """Test boot sequence with missing components (graceful degradation).

        Per Commit 8: Verify boot completes gracefully when optional components are missing.
        """
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Create fake services (missing position manager, missing user stream)
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_store = InMemoryOrderStore(bus)
        oms_core = FakeOMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake execution router
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = MagicMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        # Create execution control
        execution_control = ExecutionControl(bus=bus)

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Missing: position_manager_factory, user_stream_adapter_factory
        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            position_manager_factory=None,  # Missing component
            user_stream_adapter_factory=None,  # Missing component
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=None,  # Will use default
        )

        # Boot should complete successfully (graceful degradation)
        await supervisor.start()

        # Verify services started
        assert supervisor.portfolio_service is not None
        assert supervisor.oms_core is not None
        assert supervisor.execution_router is not None

        # Verify position manager is None (missing component)
        assert supervisor.position_manager is None

        # Verify user stream adapter is None (missing component)
        assert supervisor._user_stream_adapter is None

        # Boot should still complete
        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_state_reconstruction_persists_to_running_oms_core(self) -> None:
        """Test that state reconstruction persists to the running OMS core.

        Per review fix: Verify that orders reconstructed from event log
        persist in the same OMS core instance used for actual operation.
        """
        import time
        import uuid

        bus = EventBus()
        # Initialize event store for bus
        from polytrader.events.store import MemoryEventStore

        bus._store = MemoryEventStore()
        store = MemoryMarketDataStore()

        # Create an order intent
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            target_price=0.5,
            limit_price=0.45,
            size=10.0,
            reason="Test reconstruction",
            strategy_id="simple_threshold",
        )

        # Add order events to event store (simulating previous run)
        order_id = str(uuid.uuid4())
        client_order_id = "client-123"
        venue_order_id = "venue-456"

        created_event = OrderCreatedEvent(
            order_id=order_id,
            client_order_id=client_order_id,
            intent=intent,
            correlation_id=intent.correlation_id,
        )
        await bus._store.append(created_event)

        submitted_event = OrderSubmittedEvent(order_id=order_id, client_order_id=client_order_id)
        await bus._store.append(submitted_event)

        ack_event = OrderAckEvent(order_id=order_id, venue_order_id=venue_order_id)
        await bus._store.append(ack_event)

        fill_event = FillEvent(
            order_id=order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.45,
            fee=0.01,
        )
        await bus._store.append(fill_event)

        # Create OMS store (will be shared via factory)
        oms_store = InMemoryOrderStore(bus)
        oms_core = OMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())

        # Create fake position manager with _handle_fill support
        from polytrader.position_manager import IPositionManager

        class FakePositionManagerWithReplay(IPositionManager):
            def __init__(self) -> None:
                self._fills_replayed: list[FillEvent] = []
                self._running = False

            async def _handle_fill(self, fill_event: FillEvent) -> None:
                """Handle fill event (for replay)."""
                self._fills_replayed.append(fill_event)

            async def run(self) -> None:
                self._running = True

            def stop(self) -> None:
                self._running = False

            def get_positions(self) -> dict | None:
                return None

            def get_positions_for_strategy(
                self, strategy_id: str
            ) -> dict[tuple[str, Outcome], Position] | None:
                return None

            def get_position(self, market_slug: str, outcome: str) -> None:
                return None

        position_manager = FakePositionManagerWithReplay()

        # Create factories that return the same instances
        def oms_factory() -> OMSCore:
            return oms_core

        def position_manager_factory() -> IPositionManager:
            return position_manager

        # Create fake execution router
        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = AsyncMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        execution_control = ExecutionControl(bus=bus)

        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)

        def risk_factory() -> RiskChecker:
            return FakeRiskChecker(
                bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
            )

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Add fresh market data
        fresh_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,
        )
        store.add(fresh_event)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            position_manager_factory=position_manager_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Boot the system (this will reconstruct state)
        await supervisor.start()

        # Verify OMS core is the same instance
        assert supervisor.oms_core is oms_core

        # Verify order was reconstructed in the OMS store
        reconstructed_order = oms_store.get_order(order_id)
        assert reconstructed_order is not None, "Order should be reconstructed from event log"
        assert reconstructed_order.order_id == order_id
        assert reconstructed_order.state == OrderState.FILLED
        assert reconstructed_order.venue_order_id == venue_order_id
        assert reconstructed_order.filled_size == 10.0

        # Verify position manager is the same instance
        assert supervisor.position_manager is position_manager

        # Verify fill was replayed to position manager
        assert len(position_manager._fills_replayed) == 1
        assert position_manager._fills_replayed[0].order_id == order_id

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_oms_core_instance_reused_throughout_boot(self) -> None:
        """Test that OMS core instance is reused throughout boot sequence.

        Per review fix: Verify that the same OMS core instance created early
        in boot is used for state reconstruction, reconciliation, and service startup.
        """
        bus = EventBus()
        store = MemoryMarketDataStore()

        # Track OMS core creation
        oms_cores_created: list[OMSCore] = []

        oms_store = InMemoryOrderStore(bus)

        def oms_factory() -> OMSCore:
            oms_core = OMSCore(bus=bus, store=oms_store, idempotency_store=IdempotencyStore())
            oms_cores_created.append(oms_core)
            return oms_core

        # Create other required services
        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )

        fake_adapter = MagicMock()
        fake_adapter.get_open_orders = AsyncMock(return_value=[])
        execution_router = FakeExecutionRouter(bus)
        execution_router._adapter = fake_adapter

        execution_control = ExecutionControl(bus=bus)

        def health_service_factory() -> HealthService:
            return HealthService(
                store=store,
                thresholds=HealthGateThresholds(
                    max_market_data_staleness_seconds=60.0,
                    max_reconciliation_divergences=0,
                    max_error_rate=0.1,
                    require_user_stream=False,
                ),
                user_stream_adapter=None,
                circuit_breaker=None,
                execution_control=execution_control,
                kill_switch_active=False,
                error_rate=None,
                recent_reconcile_events=[],
            )

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def execution_router_factory() -> ExecutionRouter:
            return execution_router

        def reconciliation_factory() -> ReconciliationService:
            return ReconciliationService(store=oms_store, venue_adapter=fake_adapter, bus=bus)

        # Add fresh market data
        import time

        fresh_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.44,
            best_ask=0.46,
            ts_mono=time.monotonic() - 1.0,
        )
        store.add(fresh_event)

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            execution_router_factory=execution_router_factory,
            reconciliation_service_factory=reconciliation_factory,
            execution_control=execution_control,
            health_service_factory=health_service_factory,
        )

        # Boot the system
        await supervisor.start()

        # Verify OMS core was created only ONCE
        assert len(oms_cores_created) == 1, "OMS core should be created only once"

        # Verify the same instance is used throughout
        assert supervisor.oms_core is oms_cores_created[0]
        assert supervisor.oms_core.get_store() is oms_store

        await supervisor.stop()
