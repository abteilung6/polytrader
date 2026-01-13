"""Tests for SystemSupervisor.

Tests service lifecycle management, startup/shutdown order, and error handling.
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from polytrader.adapters.polymarket.user_stream import UserStreamAdapter
from polytrader.clob import IClobClient
from polytrader.events import (
    CIRCUIT_BREAKER,
    EventBus,
)
from polytrader.execution import ExecutionRouter
from polytrader.oms import InMemoryOrderStore, OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.reconcile import ReconciliationService
from polytrader.ops import CircuitBreaker, CircuitBreakerThresholds, ExecutionControl
from polytrader.portfolio import PortfolioService
from polytrader.position_manager import IPositionManager
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

    def __init__(self, bus: EventBus) -> None:
        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        fake_adapter = MagicMock(spec=ClobVenueAdapter)
        super().__init__(bus=bus, adapter=fake_adapter)
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


class FakePositionManager(IPositionManager):
    """Fake PositionManager for testing."""

    def __init__(self) -> None:
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

    def get_positions(self) -> dict[tuple[str, Outcome], Position] | None:
        """Return None for testing."""
        return None

    def get_position(self, market_slug: str, outcome: Outcome) -> Position | None:
        """Return None for testing."""
        return None


class TestSystemSupervisor:
    """Tests for SystemSupervisor."""

    @pytest.mark.asyncio
    async def test_supervisor_creates_services_from_factories(self) -> None:
        """Test that supervisor creates services from factories."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        await supervisor.start()

        assert supervisor.portfolio_service is portfolio_service
        assert supervisor.risk_checker is risk_checker
        assert supervisor.oms_core is oms_core

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_starts_services_in_correct_order(self) -> None:
        """Test that services start in correct order (subscribers before publishers)."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        start_order = []

        class OrderedPortfolioService(FakePortfolioService):
            async def start(self) -> None:
                start_order.append("portfolio")
                await super().start()

        class OrderedRiskChecker(FakeRiskChecker):
            async def run(self) -> None:
                start_order.append("risk")
                await super().run()

        class OrderedOMSCore(FakeOMSCore):
            async def run(self) -> None:
                start_order.append("oms")
                await super().run()

        portfolio_service = OrderedPortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = OrderedRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = OrderedOMSCore(
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
        )

        await supervisor.start()
        await asyncio.sleep(0.05)  # Give services time to start

        # Verify order: PortfolioService → RiskChecker → OMSCore
        assert start_order == ["portfolio", "risk", "oms"]

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_stops_services_in_reverse_order(self) -> None:
        """Test that services stop in reverse order (publishers before subscribers)."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        stop_order = []

        class OrderedPortfolioService(FakePortfolioService):
            async def stop(self) -> None:
                stop_order.append("portfolio")
                await super().stop()

        class OrderedRiskChecker(FakeRiskChecker):
            def stop(self) -> None:
                stop_order.append("risk")
                super().stop()

        class OrderedOMSCore(FakeOMSCore):
            def stop(self) -> None:
                stop_order.append("oms")
                super().stop()

        portfolio_service = OrderedPortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = OrderedRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = OrderedOMSCore(
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
        )

        await supervisor.start()
        await asyncio.sleep(0.01)
        await supervisor.stop()
        await asyncio.sleep(0.05)  # Give services time to stop

        # Verify reverse order:
        # PositionManager → ExecutionRouter → OMSCore → RiskChecker → PortfolioService
        # (We only have PortfolioService, RiskChecker, OMSCore in this test)
        assert "oms" in stop_order
        assert "risk" in stop_order
        assert "portfolio" in stop_order
        # Verify order: oms stops before risk, risk stops before portfolio
        assert stop_order.index("oms") < stop_order.index("risk")
        assert stop_order.index("risk") < stop_order.index("portfolio")

    @pytest.mark.asyncio
    async def test_supervisor_handles_optional_execution_router(self) -> None:
        """Test that supervisor handles optional ExecutionRouter."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )
        execution_router = FakeExecutionRouter(bus=bus)

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
        )

        await supervisor.start()
        await asyncio.sleep(0.01)

        assert supervisor.execution_router is execution_router
        assert execution_router.run_called

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_handles_optional_position_manager(self) -> None:
        """Test that supervisor handles optional PositionManager."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )
        position_manager = FakePositionManager()

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def position_manager_factory() -> IPositionManager:
            return position_manager

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            position_manager_factory=position_manager_factory,
        )

        await supervisor.start()
        await asyncio.sleep(0.01)

        assert supervisor.position_manager is position_manager
        assert position_manager.run_called

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_get_position_manager(self) -> None:
        """Test that get_position_manager returns the position manager."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        portfolio_service = FakePortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
        risk_checker = FakeRiskChecker(
            bus=bus, engine=RiskEngine(limits=get_default_limits()), store=store
        )
        oms_core = FakeOMSCore(
            bus=bus, store=InMemoryOrderStore(bus), idempotency_store=IdempotencyStore()
        )
        position_manager = FakePositionManager()

        def portfolio_factory() -> PortfolioService:
            return portfolio_service

        def risk_factory() -> RiskChecker:
            return risk_checker

        def oms_factory() -> OMSCore:
            return oms_core

        def position_manager_factory() -> IPositionManager:
            return position_manager

        supervisor = SystemSupervisor(
            bus=bus,
            store=store,
            portfolio_service_factory=portfolio_factory,
            risk_checker_factory=risk_factory,
            oms_core_factory=oms_factory,
            position_manager_factory=position_manager_factory,
        )

        # Before start, position_manager should be None
        assert supervisor.get_position_manager() is None

        await supervisor.start()
        await asyncio.sleep(0.01)

        # After start, position_manager should be available
        assert supervisor.get_position_manager() is position_manager

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_run_waits_for_services(self) -> None:
        """Test that run() waits for service tasks to complete."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        await supervisor.start()

        # Run supervisor in background
        run_task = asyncio.create_task(supervisor.run())

        # Wait a bit to ensure services are running
        await asyncio.sleep(0.05)

        # Verify services are running
        assert risk_checker.run_called
        assert oms_core.run_called

        # Stop supervisor (should stop services and complete run())
        await supervisor.stop()

        # Wait for run() to complete
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except TimeoutError:
            pytest.fail("run() did not complete after stop()")

    @pytest.mark.asyncio
    async def test_supervisor_run_raises_if_not_started(self) -> None:
        """Test that run() raises RuntimeError if not started."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        with pytest.raises(RuntimeError, match="not started"):
            await supervisor.run()

    @pytest.mark.asyncio
    async def test_supervisor_idempotent_start(self) -> None:
        """Test that start() is idempotent (can be called multiple times)."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        # Start twice
        await supervisor.start()
        await supervisor.start()  # Should not raise

        # Verify services are still running
        assert portfolio_service.start_called
        assert risk_checker.run_called
        assert oms_core.run_called

        await supervisor.stop()

    @pytest.mark.asyncio
    async def test_supervisor_idempotent_stop(self) -> None:
        """Test that stop() is idempotent (can be called multiple times)."""
        bus = EventBus()
        store = MemoryMarketDataStore()

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
        )

        await supervisor.start()
        await asyncio.sleep(0.01)

        # Stop twice
        await supervisor.stop()
        await supervisor.stop()  # Should not raise

        # Verify services were stopped
        assert portfolio_service.stop_called
        assert risk_checker.stop_called
        assert oms_core.stop_called

    @pytest.mark.asyncio
    async def test_supervisor_handles_service_startup_errors(self) -> None:
        """Test that supervisor handles errors during service startup."""
        bus = EventBus()
        store = MemoryMarketDataStore()

        class FailingPortfolioService(FakePortfolioService):
            async def start(self) -> None:
                raise RuntimeError("Startup failed")

        portfolio_service = FailingPortfolioService(bus=bus, store=store, fixed_size_usd=1.0)
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
        )

        # Start should raise the error (now wrapped in FatalSupervisorError)
        from polytrader.supervisor.errors import FatalSupervisorError

        with pytest.raises(FatalSupervisorError, match="Startup failed"):
            await supervisor.start()

        # Supervisor sets _running = True before calling service.start(),
        # so _running will be True even if startup fails.
        # The important thing is that the error is propagated.
        assert supervisor._running
        # Verify PortfolioService was not successfully started
        assert not portfolio_service.start_called

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

        # Create fake CLOB client
        fake_clob_client = MagicMock(spec=IClobClient)
        fake_clob_client.create_or_derive_api_creds.return_value = {
            "apiKey": "test-key",
            "secret": "test-secret",
            "passphrase": "test-pass",
        }

        # Create user stream adapter factory
        def user_stream_factory() -> UserStreamAdapter:
            return UserStreamAdapter(clob_client=fake_clob_client, bus=bus)

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

        # Verify user stream adapter was created
        assert supervisor._user_stream_adapter is not None
        assert supervisor._user_stream_task is not None

        # Mock the WebSocket connection to avoid actual network calls
        with patch("polytrader.adapters.polymarket.user_stream.websockets.connect") as mock_connect:
            # Create a fake WebSocket that sends a message
            fake_ws = MagicMock()
            fake_ws.__aenter__ = MagicMock(return_value=fake_ws)
            fake_ws.__aexit__ = MagicMock(return_value=None)
            fake_ws.send = MagicMock()
            fake_ws.__aiter__ = MagicMock(return_value=iter([]))
            mock_connect.return_value = fake_ws

            # Wait a bit for the adapter to start
            await asyncio.sleep(0.1)

            # Verify adapter is running (it should have tried to connect)
            # The actual connection will fail in test, but we verify the task is running
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
        from polytrader.events.types import ReconcileEvent

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
        """Test that execution control works correctly."""
        execution_control = ExecutionControl()

        # Initially disabled
        assert not execution_control.is_enabled()

        # Enable
        execution_control.enable()
        assert execution_control.is_enabled()

        # Disable
        execution_control.disable()
        assert not execution_control.is_enabled()

        # Enable again
        execution_control.enable()
        assert execution_control.is_enabled()
