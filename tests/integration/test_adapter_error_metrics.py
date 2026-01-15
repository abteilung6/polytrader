"""Integration tests for adapter error metrics in execution and adapters.

Per Commit 14: Integrate adapter error metrics in execution and adapters.
Per observability.mdc §4: Error metrics are critical for reliability monitoring.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from polytrader.adapters.polymarket.models import VenueError
from polytrader.events import CANCEL_ORDER_COMMANDS, SUBMIT_ORDER_COMMANDS
from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import OrderIntentEvent
from polytrader.execution.router import ExecutionRouter
from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    set_metrics_collector,
)
from polytrader.oms.commands import CancelOrderCommand, SubmitOrderCommand


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def metrics_collector() -> MemoryMetricsCollector:
    """Create a metrics collector for testing."""
    collector = MemoryMetricsCollector()
    set_metrics_collector(collector)
    return collector


@pytest.fixture
def fake_adapter() -> MagicMock:
    """Create a fake venue adapter for testing."""
    adapter = MagicMock()
    adapter.submit_order = AsyncMock()
    adapter.cancel_order = AsyncMock()
    return adapter


@pytest.fixture
def execution_router(bus: EventBus, fake_adapter: MagicMock) -> ExecutionRouter:
    """Create an execution router for testing."""
    return ExecutionRouter(bus=bus, adapter=fake_adapter)


class TestExecutionRouterAdapterErrorMetrics:
    """Tests for adapter error metrics in ExecutionRouter."""

    @pytest.mark.asyncio
    async def test_submit_order_fatal_error_emits_metric(
        self,
        execution_router: ExecutionRouter,
        fake_adapter: MagicMock,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that fatal errors in submit_order emit adapter_errors_total metric."""
        # Configure adapter to raise fatal VenueError
        fake_adapter.submit_order.side_effect = VenueError(
            error_type="fatal",
            message="Insufficient balance",
            raw_error=ValueError("Insufficient balance"),
        )

        # Create submit command
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
        )
        command = SubmitOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id="corr-123",
        )

        # Start execution router
        router_task = None
        try:
            router_task = asyncio.create_task(execution_router.run())
            await asyncio.sleep(0.05)

            # Publish command
            await execution_router._bus.publish(SUBMIT_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify metric was emitted
            assert (
                metrics_collector.get_counter("adapter_errors_total", labels={"class": "fatal"})
                == 1
            )
        finally:
            if router_task:
                execution_router.stop()
                router_task.cancel()
                try:
                    await router_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_submit_order_retryable_error_emits_metric(
        self,
        execution_router: ExecutionRouter,
        fake_adapter: MagicMock,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that retryable errors in submit_order emit adapter_errors_total metric."""
        # Configure adapter to raise retryable VenueError
        fake_adapter.submit_order.side_effect = VenueError(
            error_type="retryable",
            message="Connection timeout",
            raw_error=TimeoutError("Connection timeout"),
        )

        # Create submit command
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
        )
        command = SubmitOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id="corr-123",
        )

        # Start execution router
        router_task = None
        try:
            router_task = asyncio.create_task(execution_router.run())
            await asyncio.sleep(0.05)

            # Publish command
            await execution_router._bus.publish(SUBMIT_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify metric was emitted
            assert (
                metrics_collector.get_counter("adapter_errors_total", labels={"class": "retryable"})
                == 1
            )
        finally:
            if router_task:
                execution_router.stop()
                router_task.cancel()
                try:
                    await router_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_tactic_failure_emits_fatal_metric(
        self,
        execution_router: ExecutionRouter,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that tactic failures emit adapter_errors_total metric with fatal class."""
        # Create submit command that will fail throttle check
        # (by setting throttle to reject all orders)
        from polytrader.execution.tactics import ExecutionTactics
        from polytrader.execution.throttle import ExecutionThrottle

        # Create a throttle that rejects all orders
        throttle = ExecutionThrottle(max_orders_per_second=0.0)
        execution_router._tactics = ExecutionTactics(throttle=throttle)

        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            correlation_id="corr-123",
        )
        command = SubmitOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id="corr-123",
        )

        # Start execution router
        router_task = None
        try:
            router_task = asyncio.create_task(execution_router.run())
            await asyncio.sleep(0.05)

            # Publish command
            await execution_router._bus.publish(SUBMIT_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify metric was emitted
            assert (
                metrics_collector.get_counter("adapter_errors_total", labels={"class": "fatal"})
                == 1
            )
        finally:
            if router_task:
                execution_router.stop()
                router_task.cancel()
                try:
                    await router_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_cancel_order_error_emits_metric(
        self,
        execution_router: ExecutionRouter,
        fake_adapter: MagicMock,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that errors in cancel_order emit adapter_errors_total metric."""
        # Configure adapter to raise VenueError on cancel
        fake_adapter.cancel_order.side_effect = VenueError(
            error_type="fatal",
            message="Order not found",
            raw_error=ValueError("Order not found"),
        )

        # Create cancel command
        command = CancelOrderCommand(
            order_id="order-123",
            client_order_id="client-123",
            venue_order_id="venue-123",
            correlation_id="corr-123",
        )

        # Start execution router
        router_task = None
        try:
            router_task = asyncio.create_task(execution_router.run())
            await asyncio.sleep(0.05)

            # Publish command
            await execution_router._bus.publish(CANCEL_ORDER_COMMANDS, command)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify metric was emitted
            assert (
                metrics_collector.get_counter("adapter_errors_total", labels={"class": "fatal"})
                == 1
            )
        finally:
            if router_task:
                execution_router.stop()
                router_task.cancel()
                try:
                    await router_task
                except asyncio.CancelledError:
                    pass


class TestAdapterErrorMetrics:
    """Tests for adapter error metrics in ClobVenueAdapter."""

    @pytest.mark.asyncio
    async def test_submit_order_error_emits_metric(
        self,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that errors in adapter submit_order emit metric."""
        from unittest.mock import MagicMock

        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        # Create adapter with mocked clients
        clob_client = MagicMock()
        gamma_client = MagicMock()

        # Configure gamma_client to raise an error
        gamma_client.get_market_by_slug = MagicMock(side_effect=Exception("Network error"))

        adapter = ClobVenueAdapter(clob_client=clob_client, gamma_client=gamma_client)

        # Create intent
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,
            limit_price=0.5,
            target_price=0.5,
            reason="Test order",
            correlation_id="corr-123",
        )

        # Submit order (should raise VenueError)
        with pytest.raises(VenueError):
            await adapter.submit_order("client-123", intent)

        # Verify metric was emitted (error should be classified as retryable for network errors)
        assert (
            metrics_collector.get_counter("adapter_errors_total", labels={"class": "retryable"})
            == 1
        )

    @pytest.mark.asyncio
    async def test_insufficient_balance_emits_fatal_metric(
        self,
        metrics_collector: MemoryMetricsCollector,
    ) -> None:
        """Test that insufficient balance errors emit fatal metric."""
        from unittest.mock import MagicMock

        from polytrader.adapters.polymarket.trading import ClobVenueAdapter

        # Create adapter with mocked clients
        clob_client = MagicMock()
        gamma_client = MagicMock()

        # Configure market lookup to succeed
        market_mock = MagicMock()
        market_mock.get_token_id = MagicMock(return_value="token-123")
        gamma_client.get_market_by_slug = MagicMock(return_value=market_mock)

        # Configure balance check to return insufficient balance
        clob_client.get_balance_allowance = MagicMock(
            return_value={"balance": "50.0"}  # Less than required
        )

        adapter = ClobVenueAdapter(clob_client=clob_client, gamma_client=gamma_client)

        # Create intent with size > balance
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=100.0,  # More than balance of 50.0
            limit_price=0.5,
            correlation_id="corr-123",
        )

        # Submit order (should raise ValueError for insufficient balance)
        with pytest.raises(ValueError, match="Insufficient balance"):
            await adapter.submit_order("client-123", intent)

        # Verify metric was emitted with fatal class
        assert metrics_collector.get_counter("adapter_errors_total", labels={"class": "fatal"}) == 1
