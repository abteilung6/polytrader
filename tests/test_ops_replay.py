"""Tests for state reconstruction service."""

import time
from typing import Any

import pytest

from polytrader.events import EventBus, MemoryEventStore
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
from polytrader.ops.replay import StateReconstructionService
from polytrader.types import Outcome, Position


class FakePositionManager:
    """Fake position manager for testing."""

    def __init__(self) -> None:
        """Initialize fake position manager."""
        self._fills_replayed: list[FillEvent] = []
        self._positions: dict[tuple[str, Outcome], Position] = {}
        self._running = False

    async def _handle_fill(self, fill_event: FillEvent) -> None:
        """Handle fill event (for replay)."""
        self._fills_replayed.append(fill_event)

    async def run(self) -> None:
        """Start the position manager (required by IPositionManager)."""
        self._running = True

    def stop(self) -> None:
        """Stop the position manager (required by IPositionManager)."""
        self._running = False

    def get_positions(self) -> dict[tuple[str, Outcome], Position] | None:
        """Get positions."""
        return self._positions if self._positions else None

    def get_position(self, market_slug: str, outcome: Outcome) -> Position | None:
        """Get position for a specific market and outcome."""
        key = (market_slug, outcome)
        return self._positions.get(key)


@pytest.fixture
def bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def event_store() -> MemoryEventStore:
    """Create event store for testing."""
    return MemoryEventStore()


@pytest.fixture
def oms_store(bus: EventBus) -> InMemoryOrderStore:
    """Create OMS store for testing."""
    return InMemoryOrderStore(bus=bus)


@pytest.fixture
def fake_position_manager() -> FakePositionManager:
    """Create fake position manager for testing."""
    return FakePositionManager()


@pytest.fixture
def reconstruction_service(
    event_store: MemoryEventStore,
    oms_store: InMemoryOrderStore,
    fake_position_manager: FakePositionManager,
) -> StateReconstructionService:
    """Create state reconstruction service for testing."""
    return StateReconstructionService(
        event_store=event_store,
        oms_store=oms_store,
        position_manager=fake_position_manager,
    )


@pytest.mark.asyncio
async def test_oms_reconstruction_empty_event_store(
    reconstruction_service: StateReconstructionService,
) -> None:
    """Test OMS reconstruction with empty event store."""
    await reconstruction_service.reconstruct_oms()

    # OMS store should be empty
    assert len(reconstruction_service._oms_store.get_all_orders()) == 0
    assert len(reconstruction_service._oms_store.get_open_orders()) == 0


@pytest.mark.asyncio
async def test_oms_reconstruction_from_events(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test OMS reconstruction from event log."""
    # Create a sequence of order events
    ts = time.monotonic()

    # Order created
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    # Order submitted
    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    # Order acked
    order_acked = OrderAckEvent(
        order_id="order-1",
        venue_order_id="venue-1",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_acked)

    # Reconstruct OMS
    await reconstruction_service.reconstruct_oms()

    # Verify order was reconstructed
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    order = orders[0]
    assert order.order_id == "order-1"
    assert order.client_order_id == "client-1"
    assert order.venue_order_id == "venue-1"
    assert order.state == OrderState.ACKED


@pytest.mark.asyncio
async def test_oms_reconstruction_with_fill(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test OMS reconstruction with fill event."""
    ts = time.monotonic()

    # Create order
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    # Submit
    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    # Ack
    order_acked = OrderAckEvent(
        order_id="order-1",
        venue_order_id="venue-1",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_acked)

    # Fill
    fill_event = FillEvent(
        order_id="order-1",
        fill_id="fill-1",
        size=1.0,
        price=0.45,
        fee=0.01,
        ts_mono=ts + 0.3,
    )
    await event_store.append(fill_event)

    # Reconstruct OMS
    await reconstruction_service.reconstruct_oms()

    # Verify order was filled
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    order = orders[0]
    assert order.state == OrderState.FILLED
    assert order.filled_size == 1.0


@pytest.mark.asyncio
async def test_oms_reconstruction_with_reject(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test OMS reconstruction with reject event."""
    ts = time.monotonic()

    # Create order
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    # Submit
    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    # Reject
    order_rejected = OrderRejectedEvent(
        order_id="order-1",
        reason="INSUFFICIENT_BALANCE",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_rejected)

    # Reconstruct OMS
    await reconstruction_service.reconstruct_oms()

    # Verify order was rejected
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    order = orders[0]
    assert order.state == OrderState.REJECTED


@pytest.mark.asyncio
async def test_oms_reconstruction_with_cancel(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test OMS reconstruction with cancel event."""
    ts = time.monotonic()

    # Create order
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    # Submit
    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    # Ack
    order_acked = OrderAckEvent(
        order_id="order-1",
        venue_order_id="venue-1",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_acked)

    # Cancel
    order_canceled = OrderCanceledEvent(
        order_id="order-1",
        reason="USER_REQUESTED",
        ts_mono=ts + 0.3,
    )
    await event_store.append(order_canceled)

    # Reconstruct OMS
    await reconstruction_service.reconstruct_oms()

    # Verify order was canceled
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    order = orders[0]
    assert order.state == OrderState.CANCELLED


@pytest.mark.asyncio
async def test_oms_reconstruction_out_of_order_events(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test OMS reconstruction with out-of-order events (should sort by ts_mono)."""
    ts = time.monotonic()

    # Append events out of order
    order_acked = OrderAckEvent(
        order_id="order-1",
        venue_order_id="venue-1",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_acked)

    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    # Reconstruct OMS (should handle out-of-order gracefully)
    await reconstruction_service.reconstruct_oms()

    # Verify order was reconstructed correctly
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    order = orders[0]
    assert order.order_id == "order-1"
    assert order.state == OrderState.ACKED


@pytest.mark.asyncio
async def test_position_reconstruction_empty_event_store(
    reconstruction_service: StateReconstructionService,
) -> None:
    """Test position reconstruction with empty event store."""
    await reconstruction_service.reconstruct_positions()

    # Position manager should have no fills replayed
    assert isinstance(reconstruction_service._position_manager, FakePositionManager)
    assert len(reconstruction_service._position_manager._fills_replayed) == 0


@pytest.mark.asyncio
async def test_position_reconstruction_from_fills(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    oms_store: InMemoryOrderStore,
    bus: Any,
) -> None:
    """Test position reconstruction from FillEvents."""
    ts = time.monotonic()

    # First, create an order in OMS store (needed for fill replay)
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )

    order = await oms_store.create_order(intent, "client-1")
    order.venue_order_id = "venue-1"
    oms_store.update_order(order)

    # Create fill event
    fill_event = FillEvent(
        order_id=order.order_id,
        fill_id="fill-1",
        size=1.0,
        price=0.45,
        fee=0.01,
        ts_mono=ts + 0.1,
    )
    await event_store.append(fill_event)

    # Reconstruct positions
    await reconstruction_service.reconstruct_positions()

    # Verify fill was replayed
    assert isinstance(reconstruction_service._position_manager, FakePositionManager)
    assert len(reconstruction_service._position_manager._fills_replayed) == 1
    assert reconstruction_service._position_manager._fills_replayed[0].fill_id == "fill-1"


@pytest.mark.asyncio
async def test_position_reconstruction_missing_order(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    bus: Any,
) -> None:
    """Test position reconstruction with FillEvent referencing unknown order."""
    ts = time.monotonic()

    # Create fill event for unknown order
    fill_event = FillEvent(
        order_id="unknown-order",
        fill_id="fill-1",
        size=1.0,
        price=0.45,
        fee=0.01,
        ts_mono=ts,
    )
    await event_store.append(fill_event)

    # Reconstruct positions (should handle gracefully)
    await reconstruction_service.reconstruct_positions()

    # Fill should not be replayed (order not found)
    assert isinstance(reconstruction_service._position_manager, FakePositionManager)
    assert len(reconstruction_service._position_manager._fills_replayed) == 0


@pytest.mark.asyncio
async def test_reconstruct_all(
    reconstruction_service: StateReconstructionService,
    event_store: MemoryEventStore,
    oms_store: InMemoryOrderStore,
    bus: Any,
) -> None:
    """Test full state reconstruction (OMS + positions)."""
    ts = time.monotonic()

    # Create order events
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )
    order_created = OrderCreatedEvent(
        order_id="order-1",
        client_order_id="client-1",
        intent=intent,
    )
    await event_store.append(order_created)

    order_submitted = OrderSubmittedEvent(
        order_id="order-1",
        client_order_id="client-1",
        ts_mono=ts + 0.1,
    )
    await event_store.append(order_submitted)

    order_acked = OrderAckEvent(
        order_id="order-1",
        client_order_id="client-1",
        venue_order_id="venue-1",
        ts_mono=ts + 0.2,
    )
    await event_store.append(order_acked)

    # Create order in OMS store for fill replay
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        target_price=0.50,
        limit_price=0.45,
        size=1.0,
        reason="Test order",
        ts_mono=ts,
        strategy_id="simple_threshold",
    )

    order = await oms_store.create_order(intent, "client-1")
    order.venue_order_id = "venue-1"
    oms_store.update_order(order)

    # Create fill event
    fill_event = FillEvent(
        order_id="order-1",
        fill_id="fill-1",
        size=1.0,
        price=0.45,
        fee=0.01,
        ts_mono=ts + 0.3,
    )
    await event_store.append(fill_event)

    # Reconstruct all
    await reconstruction_service.reconstruct_all()

    # Verify OMS was reconstructed
    orders = reconstruction_service._oms_store.get_all_orders()
    assert len(orders) == 1

    # Verify positions were reconstructed
    assert isinstance(reconstruction_service._position_manager, FakePositionManager)
    assert len(reconstruction_service._position_manager._fills_replayed) == 1


@pytest.mark.asyncio
async def test_position_reconstruction_no_position_manager(
    event_store: MemoryEventStore,
    oms_store: InMemoryOrderStore,
    bus: Any,
) -> None:
    """Test position reconstruction without position manager."""
    service = StateReconstructionService(
        event_store=event_store,
        oms_store=oms_store,
        position_manager=None,
    )

    # Should not raise error
    await service.reconstruct_positions()


@pytest.mark.asyncio
async def test_position_reconstruction_position_manager_without_handle_fill(
    event_store: MemoryEventStore,
    oms_store: InMemoryOrderStore,
    bus: Any,
) -> None:
    """Test position reconstruction with position manager that doesn't support fill replay."""

    # Create a position manager without _handle_fill method
    class NoFillReplayManager:
        """Position manager without _handle_fill."""

        def get_positions(self) -> dict[tuple[str, Outcome], Any] | None:
            """Get positions."""
            return None

    service = StateReconstructionService(
        event_store=event_store,
        oms_store=oms_store,
        position_manager=NoFillReplayManager(),  # type: ignore[arg-type]
    )

    # Should not raise error, just log warning
    await service.reconstruct_positions()
