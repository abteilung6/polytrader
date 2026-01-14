"""Tests for OMS Store: Event-backed order projection.

Per flows.mdc §7: OMS store maintains order state from events.
"""

import pytest

from polytrader.events.bus import EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderIntentEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from polytrader.oms.models import OrderState
from polytrader.oms.store import InMemoryOrderStore


def create_test_intent(
    market_slug: str = "test-market",
    outcome: str = "UP",
    side: str = "BUY",
    size: float = 10.0,
    limit_price: float = 0.5,
    reason: str = "Test intent",
) -> OrderIntentEvent:
    """Create a test OrderIntentEvent."""
    return OrderIntentEvent(
        market_slug=market_slug,
        outcome=outcome,
        side=side,
        target_price=0.6,
        limit_price=limit_price,
        size=size,
        reason=reason,
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create an event bus for testing."""
    store = MemoryEventStore()
    return EventBus(store=store)


@pytest.fixture
def order_store(event_bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(event_bus)


@pytest.mark.asyncio
class TestOrderStoreCreation:
    """Tests for order creation."""

    async def test_create_order(self, order_store: InMemoryOrderStore) -> None:
        """Test creating a new order."""
        intent = create_test_intent()
        client_order_id = "client-123"

        order = await order_store.create_order(intent, client_order_id)

        assert order.client_order_id == client_order_id
        assert order.state == OrderState.NEW
        assert order.intent == intent
        assert order.market_slug == intent.market_slug
        assert order.size == intent.size

    async def test_create_order_stores_in_dict(self, order_store: InMemoryOrderStore) -> None:
        """Test that created order is stored in internal dictionary."""
        intent = create_test_intent()
        client_order_id = "client-123"

        order = await order_store.create_order(intent, client_order_id)

        # Check order is stored
        stored_order = order_store.get_order(order.order_id)
        assert stored_order is not None
        assert stored_order.order_id == order.order_id

        # Check client_order_id mapping
        stored_by_client = order_store.get_order_by_client_id(client_order_id)
        assert stored_by_client is not None
        assert stored_by_client.order_id == order.order_id

    async def test_create_order_emits_event(self, order_store: InMemoryOrderStore) -> None:
        """Test that create_order emits OrderCreatedEvent."""
        intent = create_test_intent()
        client_order_id = "client-123"

        order = await order_store.create_order(intent, client_order_id)

        # Check event history
        history = order_store.get_order_history(order.order_id)
        assert len(history) == 1
        assert isinstance(history[0], OrderCreatedEvent)
        assert history[0].order_id == order.order_id
        assert history[0].client_order_id == client_order_id


@pytest.mark.asyncio
class TestOrderStoreQueries:
    """Tests for order query methods."""

    async def test_get_order_by_id(self, order_store: InMemoryOrderStore) -> None:
        """Test getting order by order_id."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        retrieved = order_store.get_order(order.order_id)

        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    async def test_get_order_nonexistent(self, order_store: InMemoryOrderStore) -> None:
        """Test getting non-existent order returns None."""
        retrieved = order_store.get_order("nonexistent-order-id")
        assert retrieved is None

    async def test_get_order_by_client_id(self, order_store: InMemoryOrderStore) -> None:
        """Test getting order by client_order_id."""
        intent = create_test_intent()
        client_order_id = "client-123"
        order = await order_store.create_order(intent, client_order_id)

        retrieved = order_store.get_order_by_client_id(client_order_id)

        assert retrieved is not None
        assert retrieved.order_id == order.order_id
        assert retrieved.client_order_id == client_order_id

    async def test_get_order_by_client_id_nonexistent(
        self, order_store: InMemoryOrderStore
    ) -> None:
        """Test getting order by non-existent client_order_id returns None."""
        retrieved = order_store.get_order_by_client_id("nonexistent-client-id")
        assert retrieved is None

    async def test_get_open_orders(self, order_store: InMemoryOrderStore) -> None:
        """Test getting all open (non-terminal) orders."""
        # Create multiple orders
        order1 = await order_store.create_order(create_test_intent(), "client-1")
        order2 = await order_store.create_order(create_test_intent(), "client-2")
        order3 = await order_store.create_order(create_test_intent(), "client-3")

        open_orders = order_store.get_open_orders()

        assert len(open_orders) == 3
        order_ids = {o.order_id for o in open_orders}
        assert order1.order_id in order_ids
        assert order2.order_id in order_ids
        assert order3.order_id in order_ids

    async def test_get_open_orders_excludes_terminal(self, order_store: InMemoryOrderStore) -> None:
        """Test that get_open_orders excludes terminal orders."""
        order1 = await order_store.create_order(create_test_intent(), "client-1")
        order2 = await order_store.create_order(create_test_intent(), "client-2")

        # Make order2 terminal (REJECTED) - store will handle intermediate states
        from polytrader.events.types import OrderRejectedEvent

        reject_event = OrderRejectedEvent(order_id=order2.order_id, reason="Test rejection")
        # Store will automatically transition NEW → PENDING_SUBMIT → SUBMITTED → REJECTED
        order_store.handle_order_rejected(reject_event)

        open_orders = order_store.get_open_orders()

        assert len(open_orders) == 1
        assert open_orders[0].order_id == order1.order_id

    async def test_get_order_history(self, order_store: InMemoryOrderStore) -> None:
        """Test getting event history for an order."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        # Add more events
        from polytrader.events.types import OrderSubmittedEvent

        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        history = order_store.get_order_history(order.order_id)

        assert len(history) == 2
        assert isinstance(history[0], OrderCreatedEvent)
        assert isinstance(history[1], OrderSubmittedEvent)
        # Should be sorted by ts_mono
        assert history[0].ts_mono <= history[1].ts_mono


@pytest.mark.asyncio
class TestOrderStoreEventHandlers:
    """Tests for event handler methods."""

    async def testhandle_order_submitted(self, order_store: InMemoryOrderStore) -> None:
        """Test handling OrderSubmittedEvent."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        # Store should handle NEW → PENDING_SUBMIT → SUBMITTED automatically
        assert updated_order.state == OrderState.SUBMITTED

    async def testhandle_order_ack(self, order_store: InMemoryOrderStore) -> None:
        """Test handling OrderAckEvent."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        # First submit
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        # Then ack
        ack_event = OrderAckEvent(order_id=order.order_id, venue_order_id="venue-456")
        order_store.handle_order_ack(ack_event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.ACKED
        assert updated_order.venue_order_id == "venue-456"

    async def testhandle_order_rejected(self, order_store: InMemoryOrderStore) -> None:
        """Test handling OrderRejectedEvent."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        # Submit first
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        # Then reject
        reject_event = OrderRejectedEvent(order_id=order.order_id, reason="Insufficient balance")
        order_store.handle_order_rejected(reject_event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.REJECTED
        assert updated_order.reject_reason == "Insufficient balance"

    async def testhandle_fill_partial(self, order_store: InMemoryOrderStore) -> None:
        """Test handling FillEvent for partial fill."""
        intent = create_test_intent(size=10.0)
        order = await order_store.create_order(intent, "client-123")

        # Submit and ack first
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        ack_event = OrderAckEvent(order_id=order.order_id, venue_order_id="venue-456")
        order_store.handle_order_ack(ack_event)

        # Partial fill
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-1",
            size=5.0,
            price=0.45,
            fee=0.01,
        )
        order_store.handle_fill(fill_event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.PARTIALLY_FILLED
        assert updated_order.filled_size == 5.0
        assert updated_order.avg_fill_price == 0.45

    async def testhandle_fill_full(self, order_store: InMemoryOrderStore) -> None:
        """Test handling FillEvent for full fill."""
        intent = create_test_intent(size=10.0)
        order = await order_store.create_order(intent, "client-123")

        # Submit and ack first
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        ack_event = OrderAckEvent(order_id=order.order_id, venue_order_id="venue-456")
        order_store.handle_order_ack(ack_event)

        # Full fill
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.45,
            fee=0.01,
        )
        order_store.handle_fill(fill_event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.FILLED
        assert updated_order.filled_size == 10.0
        assert updated_order.avg_fill_price == 0.45

    async def testhandle_fill_multiple(self, order_store: InMemoryOrderStore) -> None:
        """Test handling multiple FillEvents (weighted average price)."""
        intent = create_test_intent(size=10.0)
        order = await order_store.create_order(intent, "client-123")

        # Submit and ack first
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        ack_event = OrderAckEvent(order_id=order.order_id, venue_order_id="venue-456")
        order_store.handle_order_ack(ack_event)

        # First fill: 5.0 @ 0.45
        fill1 = FillEvent(
            order_id=order.order_id,
            fill_id="fill-1",
            size=5.0,
            price=0.45,
            fee=0.01,
        )
        order_store.handle_fill(fill1)

        # Second fill: 5.0 @ 0.50
        fill2 = FillEvent(
            order_id=order.order_id,
            fill_id="fill-2",
            size=5.0,
            price=0.50,
            fee=0.01,
        )
        order_store.handle_fill(fill2)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.FILLED
        assert updated_order.filled_size == 10.0
        # Weighted average: (5.0 * 0.45 + 5.0 * 0.50) / 10.0 = 0.475
        assert updated_order.avg_fill_price == pytest.approx(0.475)

    async def testhandle_order_canceled(self, order_store: InMemoryOrderStore) -> None:
        """Test handling OrderCanceledEvent."""
        intent = create_test_intent()
        order = await order_store.create_order(intent, "client-123")

        # Submit and ack first
        submit_event = OrderSubmittedEvent(order_id=order.order_id, client_order_id="client-123")
        order_store.handle_order_submitted(submit_event)

        ack_event = OrderAckEvent(order_id=order.order_id, venue_order_id="venue-456")
        order_store.handle_order_ack(ack_event)

        # Cancel
        cancel_event = OrderCanceledEvent(order_id=order.order_id, reason="User requested")
        order_store.handle_order_canceled(cancel_event)

        updated_order = order_store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.CANCELLED


@pytest.mark.asyncio
class TestOrderStoreReplay:
    """Tests for event replay functionality."""

    async def test_rebuild_from_events(self, order_store: InMemoryOrderStore) -> None:
        """Test rebuilding order state from events."""
        intent = create_test_intent()

        # Create events in order
        created_event = OrderCreatedEvent(
            order_id="order-123",
            client_order_id="client-123",
            intent=intent,
            correlation_id=intent.correlation_id,
        )

        submitted_event = OrderSubmittedEvent(order_id="order-123", client_order_id="client-123")

        ack_event = OrderAckEvent(order_id="order-123", venue_order_id="venue-456")

        fill_event = FillEvent(
            order_id="order-123",
            fill_id="fill-1",
            size=10.0,
            price=0.45,
            fee=0.01,
        )

        events = [created_event, submitted_event, ack_event, fill_event]
        order_store.rebuild_from_events(events)

        # Verify order state
        order = order_store.get_order("order-123")
        assert order is not None
        assert order.state == OrderState.FILLED
        assert order.venue_order_id == "venue-456"
        assert order.filled_size == 10.0

    async def test_rebuild_from_events_clears_existing(
        self, order_store: InMemoryOrderStore
    ) -> None:
        """Test that rebuild_from_events clears existing state."""
        # Create an order
        intent1 = create_test_intent()
        await order_store.create_order(intent1, "client-1")

        intent2 = create_test_intent(market_slug="different-market")
        created_event = OrderCreatedEvent(
            order_id="order-2",
            client_order_id="client-2",
            intent=intent2,
            correlation_id=intent2.correlation_id,
        )

        order_store.rebuild_from_events([created_event])

        # Original order should be gone
        assert order_store.get_order_by_client_id("client-1") is None

        # New order should exist
        assert order_store.get_order_by_client_id("client-2") is not None

    async def test_rebuild_from_events_clears_venue_order_ids(
        self, order_store: InMemoryOrderStore
    ) -> None:
        """Test that rebuild_from_events clears stale venue_order_id mappings.

        Per review fix: Verify that _venue_order_ids is cleared during
        state reconstruction to prevent stale mappings from previous state.
        """
        from polytrader.events.types import OrderAckEvent, OrderSubmittedEvent

        # Create an order with venue_order_id (simulating previous state)
        intent1 = create_test_intent()
        order1 = await order_store.create_order(intent1, "client-1")
        # Simulate submit and ack with venue_order_id
        submitted_event1 = OrderSubmittedEvent(order_id=order1.order_id, client_order_id="client-1")
        order_store.handle_order_submitted(submitted_event1)
        ack_event1 = OrderAckEvent(order_id=order1.order_id, venue_order_id="venue-old-123")
        order_store.handle_order_ack(ack_event1)

        # Verify venue_order_id mapping exists
        assert order_store.get_order_by_venue_id("venue-old-123") is not None

        # Rebuild from events with a different order
        # Must include SUBMITTED event before ACK (FSM requirement)
        intent2 = create_test_intent(market_slug="different-market")
        created_event2 = OrderCreatedEvent(
            order_id="order-2",
            client_order_id="client-2",
            intent=intent2,
            correlation_id=intent2.correlation_id,
        )
        submitted_event2 = OrderSubmittedEvent(order_id="order-2", client_order_id="client-2")
        ack_event2 = OrderAckEvent(order_id="order-2", venue_order_id="venue-new-456")

        order_store.rebuild_from_events([created_event2, submitted_event2, ack_event2])

        # Old venue_order_id mapping should be cleared
        assert order_store.get_order_by_venue_id("venue-old-123") is None

        # New venue_order_id mapping should exist
        assert order_store.get_order_by_venue_id("venue-new-456") is not None
        order2 = order_store.get_order_by_venue_id("venue-new-456")
        assert order2 is not None
        assert order2.order_id == "order-2"
