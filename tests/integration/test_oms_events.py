"""Integration tests for OMS event emission.

Per Commit 18: Emit CancelRequestedEvent in OMS core.
Per observability.mdc §1: CancelRequestedEvent is a core event type.
"""

import asyncio
import uuid

import pytest

from polytrader.events import CANCEL_REQUESTED, EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import CancelRequestedEvent, OrderIntentEvent
from polytrader.oms.core import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.store import InMemoryOrderStore


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    """Create an idempotency store for testing."""
    return IdempotencyStore()


@pytest.fixture
def oms_core(
    bus: EventBus, order_store: InMemoryOrderStore, idempotency_store: IdempotencyStore
) -> OMSCore:
    """Create an OMS core for testing."""
    return OMSCore(bus=bus, store=order_store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create a sample order intent for testing."""
    return OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.5,
        limit_price=0.45,
        size=100.0,
        reason="Test order",
        correlation_id="corr-123",
        strategy_id="simple_threshold",
    )


class TestCancelRequestedEvent:
    """Tests for CancelRequestedEvent emission in OMS core."""

    @pytest.mark.asyncio
    async def test_cancel_requested_event_emitted_on_cancel(
        self,
        bus: EventBus,
        oms_core: OMSCore,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that CancelRequestedEvent is emitted when order is cancelled."""
        # Subscribe to cancel requested events
        cancel_requested_queue = bus.subscribe(CANCEL_REQUESTED)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED and ACKED before it can be cancelled
        from polytrader.events.types import OrderAckEvent, OrderSubmittedEvent

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Cancel the order
        await oms_core.handle_cancel("client-123", reason="Test cancellation")

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Check that CancelRequestedEvent was emitted
        assert not cancel_requested_queue.empty(), "CancelRequestedEvent was not emitted"
        cancel_requested_event = await cancel_requested_queue.get()

        assert isinstance(cancel_requested_event, CancelRequestedEvent)
        assert cancel_requested_event.order_id == order.order_id
        assert cancel_requested_event.client_order_id == "client-123"
        assert cancel_requested_event.reason == "Test cancellation"
        assert cancel_requested_event.requested_by == "system"
        assert cancel_requested_event.correlation_id == sample_intent.correlation_id

    @pytest.mark.asyncio
    async def test_cancel_requested_event_without_reason(
        self,
        bus: EventBus,
        oms_core: OMSCore,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that CancelRequestedEvent is emitted even without a reason."""
        # Subscribe to cancel requested events
        cancel_requested_queue = bus.subscribe(CANCEL_REQUESTED)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED and ACKED before it can be cancelled
        from polytrader.events.types import OrderAckEvent, OrderSubmittedEvent

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Cancel the order without a reason
        await oms_core.handle_cancel("client-123", reason=None)

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Check that CancelRequestedEvent was emitted
        assert not cancel_requested_queue.empty(), "CancelRequestedEvent was not emitted"
        cancel_requested_event = await cancel_requested_queue.get()

        assert isinstance(cancel_requested_event, CancelRequestedEvent)
        assert cancel_requested_event.order_id == order.order_id
        assert cancel_requested_event.client_order_id == "client-123"
        assert cancel_requested_event.reason is None
        assert cancel_requested_event.requested_by == "system"

    @pytest.mark.asyncio
    async def test_cancel_requested_event_before_cancel_command(
        self,
        bus: EventBus,
        oms_core: OMSCore,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that CancelRequestedEvent is emitted before CancelOrderCommand."""
        # Subscribe to both topics
        cancel_requested_queue = bus.subscribe(CANCEL_REQUESTED)
        from polytrader.events import CANCEL_ORDER_COMMANDS

        cancel_commands_queue = bus.subscribe(CANCEL_ORDER_COMMANDS)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED and ACKED before it can be cancelled
        from polytrader.events.types import OrderAckEvent, OrderSubmittedEvent

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Cancel the order
        await oms_core.handle_cancel("client-123", reason="Test")

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Both events should be emitted
        assert not cancel_requested_queue.empty(), "CancelRequestedEvent was not emitted"
        assert not cancel_commands_queue.empty(), "CancelOrderCommand was not emitted"

        # Get both events
        cancel_requested_event = await cancel_requested_queue.get()
        cancel_command = await cancel_commands_queue.get()

        # Verify CancelRequestedEvent was emitted
        assert isinstance(cancel_requested_event, CancelRequestedEvent)
        assert cancel_requested_event.order_id == order.order_id

        # Verify CancelOrderCommand was emitted
        assert cancel_command.order_id == order.order_id
        assert cancel_command.client_order_id == "client-123"

        # The CancelRequestedEvent should have the same correlation_id as the command
        assert cancel_requested_event.correlation_id == cancel_command.correlation_id

    @pytest.mark.asyncio
    async def test_cancel_requested_event_not_emitted_for_invalid_cancel(
        self,
        bus: EventBus,
        oms_core: OMSCore,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that CancelRequestedEvent is not emitted when cancel fails."""
        # Subscribe to cancel requested events
        cancel_requested_queue = bus.subscribe(CANCEL_REQUESTED)

        # Try to cancel a non-existent order
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_cancel("non-existent", reason="Test")

        # Wait a bit to ensure no events are emitted
        await asyncio.sleep(0.1)

        # Check that no CancelRequestedEvent was emitted
        assert cancel_requested_queue.empty(), (
            "CancelRequestedEvent should not be emitted for invalid cancel"
        )

    @pytest.mark.asyncio
    async def test_cancel_requested_event_not_emitted_for_terminal_order(
        self,
        bus: EventBus,
        oms_core: OMSCore,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that CancelRequestedEvent is not emitted when order is already terminal."""
        # Subscribe to cancel requested events
        cancel_requested_queue = bus.subscribe(CANCEL_REQUESTED)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED and ACKED
        from polytrader.events.types import FillEvent, OrderAckEvent, OrderSubmittedEvent

        submitted_event = OrderSubmittedEvent(
            order_id=order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Fill the order completely to make it terminal (ACKED → FILLED is valid)
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id=str(uuid.uuid4()),
            size=order.size,
            price=0.5,
            fee=0.0,
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_fill(fill_event)

        # Try to cancel a terminal order
        with pytest.raises(ValueError, match="already in terminal state"):
            await oms_core.handle_cancel("client-123", reason="Test")

        # Wait a bit to ensure no events are emitted
        await asyncio.sleep(0.1)

        # Check that no CancelRequestedEvent was emitted
        assert cancel_requested_queue.empty(), (
            "CancelRequestedEvent should not be emitted for terminal order"
        )
