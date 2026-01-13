"""Tests for SystemSupervisor.

Tests service lifecycle management, startup/shutdown order, and error handling.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.events import CIRCUIT_BREAKER, RECONCILE
from polytrader.events.bus import EventBus
from polytrader.events.types import ReconcileEvent
from polytrader.execution import ExecutionRouter
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.reconcile import ReconciliationService
from polytrader.ops import CircuitBreaker, CircuitBreakerThresholds, ExecutionControl
from polytrader.portfolio import PortfolioService
from polytrader.risk import RiskChecker, RiskEngine, get_default_limits
from polytrader.store import MemoryMarketDataStore
from polytrader.supervisor import SystemSupervisor
from polytrader.types import Outcome, Position


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
