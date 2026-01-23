"""Integration tests for ExecutionRouter strategy activation enforcement.

Per Platform_Proposal.md §2.4: Tests verify end-to-end flow where inactive
strategies are rejected by ExecutionRouter (backstop check).
"""

import asyncio
from typing import Any

import pytest

from polytrader.adapters.polymarket.models import VenueResponse
from polytrader.events import ORDER_REJECTS, SUBMIT_ORDER_COMMANDS, EventBus
from polytrader.events.types import OrderIntentEvent, OrderRejectedEvent
from polytrader.execution.router import ExecutionRouter
from polytrader.execution.tactics import ExecutionTactics
from polytrader.execution.throttle import ExecutionThrottle
from polytrader.oms.commands import SubmitOrderCommand
from tests.factories.events import create_order_intent_event


class FakeVenueAdapter:
    """Fake venue adapter for integration testing.

    Implements IVenueAdapter protocol (structural typing).
    """

    def __init__(self) -> None:
        """Initialize fake adapter."""
        self.submit_calls: list[tuple[str, OrderIntentEvent]] = []

    async def submit_order(self, client_order_id: str, intent: OrderIntentEvent) -> VenueResponse:
        """Submit order to venue."""
        self.submit_calls.append((client_order_id, intent))
        return VenueResponse(
            venue_order_id=f"venue-{client_order_id}",
            status="ACKED",
            raw_response={"order_id": f"venue-{client_order_id}"},
        )

    async def cancel_order(self, client_order_id: str, venue_order_id: str) -> VenueResponse:
        """Cancel order."""
        return VenueResponse(
            venue_order_id=venue_order_id,
            status="CANCELLED",
            raw_response={"order_id": venue_order_id},
        )

    async def get_open_orders(
        self, market_slug: str | None = None, token_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get open orders."""
        return []


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for tests."""
    return EventBus()


@pytest.fixture
def fake_adapter() -> FakeVenueAdapter:
    """Create fake adapter for tests."""
    return FakeVenueAdapter()


@pytest.fixture
def tactics() -> ExecutionTactics:
    """Create execution tactics for tests."""
    return ExecutionTactics(throttle=ExecutionThrottle())


@pytest.mark.asyncio
async def test_inactive_strategy_order_rejected(
    bus: EventBus, fake_adapter: FakeVenueAdapter, tactics: ExecutionTactics
) -> None:
    """Test end-to-end: inactive strategy → OrderRejectedEvent.

    Should not reach here if Risk works, but backstop ensures safety.
    """
    router = ExecutionRouter(
        bus=bus,
        adapter=fake_adapter,
        tactics=tactics,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
    )

    intent = create_order_intent_event(strategy_id="inactive_strategy")
    command = SubmitOrderCommand(
        order_id="order-123",
        client_order_id="client-123",
        intent=intent,
        correlation_id=intent.correlation_id,
    )

    # Subscribe to rejections
    reject_queue = bus.subscribe(ORDER_REJECTS)

    # Start router
    router_task = asyncio.create_task(router.run())
    await asyncio.sleep(0.01)  # Give time to subscribe

    try:
        # Publish command
        await bus.publish(SUBMIT_ORDER_COMMANDS, command)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check if OrderRejectedEvent was emitted
        rejected_events = []
        try:
            while True:
                event = await asyncio.wait_for(reject_queue.get(), timeout=0.1)
                rejected_events.append(event)
        except TimeoutError:
            pass

        # Should have rejected event
        assert len(rejected_events) == 1
        assert isinstance(rejected_events[0], OrderRejectedEvent)
        assert rejected_events[0].order_id == command.order_id
        assert "Strategy not active" in rejected_events[0].reason

        # Adapter should not have been called
        assert len(fake_adapter.submit_calls) == 0

    finally:
        router.stop()
        router_task.cancel()
        try:
            await router_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_active_strategy_order_submitted(
    bus: EventBus, fake_adapter: FakeVenueAdapter, tactics: ExecutionTactics
) -> None:
    """Test end-to-end: active strategy → order submitted to adapter."""
    router = ExecutionRouter(
        bus=bus,
        adapter=fake_adapter,
        tactics=tactics,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
    )

    intent = create_order_intent_event(strategy_id="active_strategy")
    command = SubmitOrderCommand(
        order_id="order-123",
        client_order_id="client-123",
        intent=intent,
        correlation_id=intent.correlation_id,
    )

    # Start router
    router_task = asyncio.create_task(router.run())
    await asyncio.sleep(0.01)  # Give time to subscribe

    try:
        # Publish command
        await bus.publish(SUBMIT_ORDER_COMMANDS, command)

        # Wait for processing
        await asyncio.sleep(0.2)

        # Adapter should have been called
        assert len(fake_adapter.submit_calls) == 1
        called_client_id, called_intent = fake_adapter.submit_calls[0]
        assert called_client_id == command.client_order_id
        assert called_intent.strategy_id == "active_strategy"

    finally:
        router.stop()
        router_task.cancel()
        try:
            await router_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_backstop_works_even_if_risk_bypassed(
    bus: EventBus, fake_adapter: FakeVenueAdapter, tactics: ExecutionTactics
) -> None:
    """Test backstop works even if Risk check is bypassed (defense in depth)."""
    # This test simulates a scenario where Risk check is bypassed
    # (e.g., RiskChecker not running or bug in Risk layer)
    # ExecutionRouter should still reject inactive strategies

    router = ExecutionRouter(
        bus=bus,
        adapter=fake_adapter,
        tactics=tactics,
        active_strategies={"active_strategy"},
        is_paper_mode=False,
    )

    # Create command from inactive strategy (bypassing Risk)
    intent = create_order_intent_event(strategy_id="inactive_strategy")
    command = SubmitOrderCommand(
        order_id="order-123",
        client_order_id="client-123",
        intent=intent,
        correlation_id=intent.correlation_id,
    )

    # Subscribe to rejections
    reject_queue = bus.subscribe(ORDER_REJECTS)

    # Start router
    router_task = asyncio.create_task(router.run())
    await asyncio.sleep(0.01)  # Give time to subscribe

    try:
        # Publish command directly (bypassing Risk)
        await bus.publish(SUBMIT_ORDER_COMMANDS, command)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check if OrderRejectedEvent was emitted
        rejected_events = []
        try:
            while True:
                event = await asyncio.wait_for(reject_queue.get(), timeout=0.1)
                rejected_events.append(event)
        except TimeoutError:
            pass

        # Should have rejected event (backstop worked)
        assert len(rejected_events) == 1
        assert isinstance(rejected_events[0], OrderRejectedEvent)
        assert "Strategy not active" in rejected_events[0].reason

        # Adapter should not have been called
        assert len(fake_adapter.submit_calls) == 0

    finally:
        router.stop()
        router_task.cancel()
        try:
            await router_task
        except asyncio.CancelledError:
            pass
