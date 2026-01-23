"""Tests for OMS Core user stream event handling.

Per Phase 6 Commit 4: OMS subscribes to user stream events and converts
canonical events to OMS events.
"""

import asyncio

import pytest

from polytrader.adapters.polymarket.models import (
    CanonicalCancel,
    CanonicalFill,
    CanonicalOrderAck,
)
from polytrader.events import (
    FILLS,
    ORDER_ACKS,
    USER_STREAM_ACKS,
    USER_STREAM_CANCELS,
    USER_STREAM_FILLS,
)
from polytrader.events.bus import EventBus
from polytrader.events.types import (
    FillEvent,
    OrderAckEvent,
    OrderIntentEvent,
)
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
    return OMSCore(bus=bus, store=store, idempotency_store=idempotency_store)


@pytest.fixture
def sample_intent() -> OrderIntentEvent:
    """Create sample order intent for testing."""
    return OrderIntentEvent(
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


class TestOMSCoreUserStream:
    """Tests for OMS Core user stream event handling."""

    @pytest.mark.asyncio
    async def test_oms_subscribes_to_user_stream(self, oms_core: OMSCore, bus: EventBus) -> None:
        """Test that OMS receives user stream events."""
        # Start OMS in background
        oms_task = asyncio.create_task(oms_core.run())

        # Give it time to subscribe
        await asyncio.sleep(0.1)

        # Publish a canonical ack
        canonical_ack = CanonicalOrderAck(
            client_order_id="test-client-123",
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:45Z",
        )
        await bus.publish(USER_STREAM_ACKS, canonical_ack)

        # Give it time to process
        await asyncio.sleep(0.1)

        # Stop OMS
        oms_core.stop()
        oms_task.cancel()
        try:
            await oms_task
        except asyncio.CancelledError:
            pass

        # Test passes if no exceptions were raised

    @pytest.mark.asyncio
    async def test_oms_handles_canonical_ack(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that OMS converts CanonicalOrderAck to OrderAckEvent."""
        # Subscribe to ORDER_ACKS to verify conversion
        ack_queue = bus.subscribe(ORDER_ACKS)

        # Create an order first
        order = await oms_core.create_order(sample_intent)

        # Start OMS in background
        oms_task = asyncio.create_task(oms_core.run())
        await asyncio.sleep(0.1)

        # Publish canonical ack with matching client_order_id
        canonical_ack = CanonicalOrderAck(
            client_order_id=order.client_order_id,
            venue_order_id="venue-456",
            timestamp="2024-01-15T10:30:45Z",
        )
        await bus.publish(USER_STREAM_ACKS, canonical_ack)

        # Wait for conversion
        try:
            ack_event = await asyncio.wait_for(ack_queue.get(), timeout=1.0)
            assert isinstance(ack_event, OrderAckEvent)
            assert ack_event.venue_order_id == "venue-456"
            assert ack_event.order_id == order.order_id

            # Verify order was updated
            updated_order = store.get_order(order.order_id)
            assert updated_order is not None
            assert updated_order.venue_order_id == "venue-456"
            assert updated_order.state == OrderState.ACKED
        except TimeoutError:
            pytest.fail("OrderAckEvent was not published")

        # Stop OMS
        oms_core.stop()
        oms_task.cancel()
        try:
            await oms_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_oms_handles_canonical_ack_by_venue_id(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that OMS can match orders by venue_order_id when client_order_id is empty."""
        # Subscribe to ORDER_ACKS
        ack_queue = bus.subscribe(ORDER_ACKS)

        # Create an order first
        order = await oms_core.create_order(sample_intent)

        # Manually set venue_order_id (simulating ack from REST API)
        order = order.model_copy(update={"venue_order_id": "venue-789"})
        store.update_order(order)

        # Start OMS in background
        oms_task = asyncio.create_task(oms_core.run())
        await asyncio.sleep(0.1)

        # Publish canonical ack with empty client_order_id but matching venue_order_id
        canonical_ack = CanonicalOrderAck(
            client_order_id="",  # Empty (as Polymarket doesn't provide it)
            venue_order_id="venue-789",  # Matches our order
            timestamp="2024-01-15T10:30:45Z",
        )
        await bus.publish(USER_STREAM_ACKS, canonical_ack)

        # Wait for conversion
        try:
            ack_event = await asyncio.wait_for(ack_queue.get(), timeout=1.0)
            assert isinstance(ack_event, OrderAckEvent)
            assert ack_event.venue_order_id == "venue-789"
        except TimeoutError:
            pytest.fail("OrderAckEvent was not published")

        # Stop OMS
        oms_core.stop()
        oms_task.cancel()
        try:
            await oms_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_oms_handles_canonical_fill(
        self,
        oms_core: OMSCore,
        bus: EventBus,
        store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that OMS converts CanonicalFill to FillEvent."""
        # Subscribe to FILLS to verify conversion
        fill_queue = bus.subscribe(FILLS)

        # Create an order first
        order = await oms_core.create_order(sample_intent)

        # Set venue_order_id (order must be acked first)
        order = order.model_copy(update={"venue_order_id": "venue-456"})
        store.update_order(order)

        # Start OMS in background
        oms_task = asyncio.create_task(oms_core.run())
        await asyncio.sleep(0.1)

        # Publish canonical fill
        canonical_fill = CanonicalFill(
            client_order_id=None,  # Not provided by Polymarket
            venue_order_id="venue-456",  # Matches our order
            fill_id="fill-789",
            size=0.5,
            price=0.55,
            fee=0.01,
            timestamp="2024-01-15T10:30:46Z",
        )
        await bus.publish(USER_STREAM_FILLS, canonical_fill)

        # Wait for conversion
        try:
            fill_event = await asyncio.wait_for(fill_queue.get(), timeout=1.0)
            assert isinstance(fill_event, FillEvent)
            assert fill_event.size == 0.5
            assert fill_event.price == 0.55
            assert fill_event.fee == 0.01
            assert fill_event.venue_fill_id == "fill-789"

            # Verify order was updated
            updated_order = store.get_order(order.order_id)
            assert updated_order is not None
            assert updated_order.filled_size == 0.5
        except TimeoutError:
            pytest.fail("FillEvent was not published")

        # Stop OMS
        oms_core.stop()
        oms_task.cancel()
        try:
            await oms_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_oms_handles_missing_order(self, oms_core: OMSCore, bus: EventBus) -> None:
        """Test that OMS handles missing orders gracefully (logs warning, doesn't crash)."""
        # Start OMS in background
        oms_task = asyncio.create_task(oms_core.run())
        await asyncio.sleep(0.1)

        # Publish canonical ack for non-existent order
        canonical_ack = CanonicalOrderAck(
            client_order_id="non-existent-client-id",
            venue_order_id="non-existent-venue-id",
            timestamp="2024-01-15T10:30:45Z",
        )
        await bus.publish(USER_STREAM_ACKS, canonical_ack)

        # Give it time to process (should log warning but not crash)
        await asyncio.sleep(0.2)

        # Publish canonical fill for non-existent order
        canonical_fill = CanonicalFill(
            client_order_id=None,
            venue_order_id="non-existent-venue-id",
            fill_id="fill-123",
            size=1.0,
            price=0.55,
            fee=0.01,
            timestamp="2024-01-15T10:30:46Z",
        )
        await bus.publish(USER_STREAM_FILLS, canonical_fill)

        # Give it time to process
        await asyncio.sleep(0.2)

        # Publish canonical cancel for non-existent order
        canonical_cancel = CanonicalCancel(
            client_order_id=None,
            venue_order_id="non-existent-venue-id",
            timestamp="2024-01-15T10:30:47Z",
        )
        await bus.publish(USER_STREAM_CANCELS, canonical_cancel)

        # Give it time to process
        await asyncio.sleep(0.2)

        # Stop OMS (should still be running)
        oms_core.stop()
        oms_task.cancel()
        try:
            await oms_task
        except asyncio.CancelledError:
            pass

        # Test passes if no exceptions were raised
