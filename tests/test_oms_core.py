"""Tests for OMS Core component."""

import asyncio
import uuid
from typing import cast

import pytest

from polytrader.events import (
    APPROVED_PROPOSALS,
    CANCEL_ORDER_COMMANDS,
    FILLS,
    ORDER_ACKS,
    ORDER_CANCELS,
    ORDER_CREATED,
    ORDER_REJECTS,
    ORDER_SUBMITTED,
    SUBMIT_ORDER_COMMANDS,
)
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderCanceledEvent,
    OrderCreatedEvent,
    OrderIntentEvent,
    OrderRejectedEvent,
)
from polytrader.oms.commands import CancelOrderCommand, SubmitOrderCommand
from polytrader.oms.core import OMSCore
from polytrader.oms.idempotency import IdempotencyStore
from polytrader.oms.models import OrderState
from polytrader.oms.store import InMemoryOrderStore


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def store(bus: EventBus) -> InMemoryOrderStore:
    """Create order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    """Create idempotency store for testing."""
    return IdempotencyStore()


@pytest.fixture
def oms_core(
    bus: EventBus, store: InMemoryOrderStore, idempotency_store: IdempotencyStore
) -> OMSCore:
    """Create OMS Core for testing."""
    return OMSCore(bus, store, idempotency_store)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create sample order intent for testing."""
    return OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=100.0,
        target_price=0.6,
        limit_price=0.5,
        correlation_id=str(uuid.uuid4()),
        ttl_s=60.0,
        reason="Test order",
    )


class TestOMSCoreOrderCreation:
    """Tests for order creation from approved intents."""

    @pytest.mark.asyncio
    async def test_create_order_emits_events_and_commands(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that order creation emits OrderCreatedEvent and SubmitOrderCommand."""
        # Capture published events/commands
        published_items: list[tuple[str, object]] = []
        original_publish = bus.publish

        async def capture_publish(topic, item):
            published_items.append((topic.name, item))
            return await original_publish(topic, item)

        bus.publish = capture_publish  # type: ignore[method-assign]

        # Create order
        order = await oms_core.create_order(sample_intent)

        # Verify order was created
        assert order is not None
        assert order.order_id is not None
        assert order.client_order_id is not None
        assert order.state == OrderState.SUBMITTED
        assert order.market_slug == sample_intent.market_slug
        assert order.outcome == sample_intent.outcome
        assert order.side == sample_intent.side
        assert order.size == sample_intent.size
        assert order.limit_price == sample_intent.limit_price

        # Verify events were emitted
        event_names = [name for name, _ in published_items]
        assert ORDER_CREATED.name in event_names
        assert ORDER_SUBMITTED.name in event_names
        assert SUBMIT_ORDER_COMMANDS.name in event_names

        # Verify OrderCreatedEvent

        created_event = cast(
            OrderCreatedEvent,
            next(item for name, item in published_items if name == ORDER_CREATED.name),
        )
        assert created_event.order_id == order.order_id
        assert created_event.client_order_id == order.client_order_id
        assert created_event.intent == sample_intent

        # Verify SubmitOrderCommand
        submit_command = cast(
            SubmitOrderCommand,
            next(item for name, item in published_items if name == SUBMIT_ORDER_COMMANDS.name),
        )
        assert submit_command.order_id == order.order_id
        assert submit_command.client_order_id == order.client_order_id
        assert submit_command.intent == sample_intent
        assert submit_command.correlation_id == sample_intent.correlation_id

    @pytest.mark.asyncio
    async def test_create_order_idempotency(
        self,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that duplicate intents return existing order."""
        # Create first order
        order1 = await oms_core.create_order(sample_intent)

        # Create duplicate order (same intent)
        order2 = await oms_core.create_order(sample_intent)

        # Should return same order
        assert order1.order_id == order2.order_id
        assert order1.client_order_id == order2.client_order_id

    @pytest.mark.asyncio
    async def test_create_order_stores_in_store(
        self,
        oms_core: OMSCore,
        store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that created order is stored in store."""
        order = await oms_core.create_order(sample_intent)

        # Verify order is in store
        stored_order = store.get_order(order.order_id)
        assert stored_order is not None
        assert stored_order.order_id == order.order_id

        # Verify can retrieve by client_order_id
        stored_by_client = store.get_order_by_client_id(order.client_order_id)
        assert stored_by_client is not None
        assert stored_by_client.order_id == order.order_id


class TestOMSCoreVenueAck:
    """Tests for handling venue acknowledgments."""

    @pytest.mark.asyncio
    async def test_handle_venue_ack_transitions_to_acked(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that venue ack transitions order to ACKED state."""
        # Create order
        order = await oms_core.create_order(sample_intent)
        client_order_id = order.client_order_id
        venue_order_id = "venue-123"

        # Capture published events
        published_items: list[tuple[str, object]] = []
        original_publish = bus.publish

        async def capture_publish(topic, item):
            published_items.append((topic.name, item))
            return await original_publish(topic, item)

        bus.publish = capture_publish  # type: ignore[method-assign]

        # Handle venue ack
        await oms_core.handle_venue_ack(client_order_id, venue_order_id)

        # Verify OrderAckEvent was emitted
        ack_event = next(item for name, item in published_items if name == ORDER_ACKS.name)
        assert isinstance(ack_event, OrderAckEvent)
        assert ack_event.order_id == order.order_id
        assert ack_event.venue_order_id == venue_order_id

        # Verify order state updated
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.ACKED
        assert updated_order.venue_order_id == venue_order_id

    @pytest.mark.asyncio
    async def test_handle_venue_ack_order_not_found(
        self,
        oms_core: OMSCore,
    ) -> None:
        """Test that venue ack raises ValueError if order not found."""
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_venue_ack("nonexistent-client-id", "venue-123")


class TestOMSCoreVenueReject:
    """Tests for handling venue rejections."""

    @pytest.mark.asyncio
    async def test_handle_venue_reject_transitions_to_rejected(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that venue reject transitions order to REJECTED state."""
        # Create order
        order = await oms_core.create_order(sample_intent)
        client_order_id = order.client_order_id
        reason = "Insufficient funds"

        # Capture published events
        published_items: list[tuple[str, object]] = []
        original_publish = bus.publish

        async def capture_publish(topic, item):
            published_items.append((topic.name, item))
            return await original_publish(topic, item)

        bus.publish = capture_publish  # type: ignore[method-assign]

        # Handle venue reject
        await oms_core.handle_venue_reject(client_order_id, reason)

        # Verify OrderRejectedEvent was emitted
        reject_event = next(item for name, item in published_items if name == ORDER_REJECTS.name)
        assert isinstance(reject_event, OrderRejectedEvent)
        assert reject_event.order_id == order.order_id
        assert reject_event.reason == reason

        # Verify order state updated
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.REJECTED
        assert updated_order.reject_reason == reason

    @pytest.mark.asyncio
    async def test_handle_venue_reject_order_not_found(
        self,
        oms_core: OMSCore,
    ) -> None:
        """Test that venue reject raises ValueError if order not found."""
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_venue_reject("nonexistent-client-id", "Some reason")


class TestOMSCoreFill:
    """Tests for handling fills."""

    @pytest.mark.asyncio
    async def test_handle_fill_partial(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that partial fill transitions order to PARTIALLY_FILLED."""
        # Create and ack order
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Capture published events
        published_items: list[tuple[str, object]] = []
        original_publish = bus.publish

        async def capture_publish(topic, item):
            published_items.append((topic.name, item))
            return await original_publish(topic, item)

        bus.publish = capture_publish  # type: ignore[method-assign]

        # Handle partial fill
        fill_size = 50.0
        fill_price = 0.55  # Probability (0-1)
        fill_fee = 0.5
        await oms_core.handle_fill(
            order.client_order_id,
            fill_size,
            fill_price,
            fill_fee,
            venue_fill_id="fill-123",
        )

        # Verify FillEvent was emitted
        fill_event = next(item for name, item in published_items if name == FILLS.name)
        assert isinstance(fill_event, FillEvent)
        assert fill_event.order_id == order.order_id
        assert fill_event.size == fill_size
        assert fill_event.price == fill_price
        assert fill_event.fee == fill_fee

        # Verify order state updated
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.PARTIALLY_FILLED
        assert updated_order.filled_size == fill_size
        assert updated_order.avg_fill_price == fill_price

    @pytest.mark.asyncio
    async def test_handle_fill_full(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that full fill transitions order to FILLED."""
        # Create and ack order
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Handle full fill
        fill_size = sample_intent.size
        fill_price = 0.55  # Probability (0-1)
        fill_fee = 1.0
        await oms_core.handle_fill(
            order.client_order_id,
            fill_size,
            fill_price,
            fill_fee,
        )

        # Verify order state updated
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.FILLED
        assert updated_order.filled_size == fill_size

    @pytest.mark.asyncio
    async def test_handle_fill_multiple(
        self,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that multiple fills accumulate correctly."""
        # Create and ack order
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # First fill: 30.0 at 0.55
        await oms_core.handle_fill(order.client_order_id, 30.0, 0.55, 0.3)
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.filled_size == 30.0
        assert updated_order.avg_fill_price == 0.55

        # Second fill: 40.0 at 0.56
        await oms_core.handle_fill(updated_order.client_order_id, 40.0, 0.56, 0.4)
        updated_order = oms_core._store.get_order(updated_order.order_id)
        assert updated_order is not None
        assert updated_order.filled_size == 70.0
        # Weighted average: (30*0.55 + 40*0.56) / 70 = 0.5557...
        expected_avg = (30.0 * 0.55 + 40.0 * 0.56) / 70.0
        assert updated_order.avg_fill_price is not None
        assert abs(updated_order.avg_fill_price - expected_avg) < 0.01

        # Third fill: 30.0 at 0.57 (completes order)
        await oms_core.handle_fill(updated_order.client_order_id, 30.0, 0.57, 0.3)
        final_order = oms_core._store.get_order(updated_order.order_id)
        assert final_order is not None
        assert final_order.state == OrderState.FILLED
        assert final_order.filled_size == 100.0

    @pytest.mark.asyncio
    async def test_handle_fill_exceeds_order_size(
        self,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that fill exceeding order size raises ValueError."""
        # Create and ack order
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Try to fill more than order size
        with pytest.raises(ValueError, match="would exceed order size"):
            await oms_core.handle_fill(order.client_order_id, 150.0, 50000.0, 1.5)

    @pytest.mark.asyncio
    async def test_handle_fill_order_not_found(
        self,
        oms_core: OMSCore,
    ) -> None:
        """Test that fill raises ValueError if order not found."""
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_fill("nonexistent-client-id", 50.0, 50000.0, 0.5)


class TestOMSCoreCancel:
    """Tests for handling order cancellations."""

    @pytest.mark.asyncio
    async def test_handle_cancel_transitions_to_cancelled(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that cancel transitions order to CANCELLED state."""
        # Create and ack order
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")

        # Capture published events/commands
        published_items: list[tuple[str, object]] = []
        original_publish = bus.publish

        async def capture_publish(topic, item):
            published_items.append((topic.name, item))
            return await original_publish(topic, item)

        bus.publish = capture_publish  # type: ignore[method-assign]

        # Handle cancel
        reason = "User requested"
        await oms_core.handle_cancel(order.client_order_id, reason)

        # Verify CancelOrderCommand was emitted
        cancel_command = cast(
            CancelOrderCommand,
            next(item for name, item in published_items if name == CANCEL_ORDER_COMMANDS.name),
        )
        assert cancel_command.order_id == order.order_id
        assert cancel_command.client_order_id == order.client_order_id
        assert cancel_command.venue_order_id == "venue-123"
        assert cancel_command.reason == reason

        # Verify OrderCanceledEvent was emitted
        cancel_event = next(item for name, item in published_items if name == ORDER_CANCELS.name)
        assert isinstance(cancel_event, OrderCanceledEvent)
        assert cancel_event.order_id == order.order_id
        assert cancel_event.reason == reason

        # Verify order state updated
        updated_order = oms_core._store.get_order(order.order_id)
        assert updated_order is not None
        assert updated_order.state == OrderState.CANCELLED

    @pytest.mark.asyncio
    async def test_handle_cancel_terminal_order(
        self,
        oms_core: OMSCore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that cancel raises ValueError if order is already terminal."""
        # Create and fill order (terminal state)
        order = await oms_core.create_order(sample_intent)
        await oms_core.handle_venue_ack(order.client_order_id, "venue-123")
        await oms_core.handle_fill(order.client_order_id, sample_intent.size, 0.55, 1.0)

        # Try to cancel terminal order
        with pytest.raises(ValueError, match="already in terminal state"):
            await oms_core.handle_cancel(order.client_order_id)

    @pytest.mark.asyncio
    async def test_handle_cancel_order_not_found(
        self,
        oms_core: OMSCore,
    ) -> None:
        """Test that cancel raises ValueError if order not found."""
        with pytest.raises(ValueError, match="Order not found"):
            await oms_core.handle_cancel("nonexistent-client-id")


class TestOMSCoreRun:
    """Tests for OMS Core async run loop."""

    @pytest.mark.asyncio
    async def test_run_processes_approved_proposals(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that run loop processes approved proposals."""
        # Start run loop in background
        run_task = asyncio.create_task(oms_core.run())

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Publish approved proposal
        await bus.publish(APPROVED_PROPOSALS, sample_intent)

        # Give it a moment to process
        await asyncio.sleep(0.01)

        # Stop run loop
        oms_core.stop()
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass

        # Verify order was created
        orders = oms_core._store.get_open_orders()
        assert len(orders) > 0
        assert any(o.market_slug == sample_intent.market_slug for o in orders)
