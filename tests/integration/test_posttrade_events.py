"""Integration tests for posttrade events (PositionUpdatedEvent, PnLEvent).

Per Commit 17: Emit PositionUpdatedEvent and PnLEvent in position manager.
Per flows.mdc §11: Post-Trade emits PositionUpdatedEvent and PnLEvent.
Per observability.mdc §1: These are core event types.
"""

import asyncio

import pytest

from polytrader.events import FILLS, MARKET_DATA, PNL_UPDATES, POSITION_UPDATES, EventBus
from polytrader.events.store import MemoryEventStore
from polytrader.events.types import (
    FillEvent,
    MarketDataEvent,
    OrderAckEvent,
    OrderIntentEvent,
    OrderSubmittedEvent,
    PnLEvent,
    PositionUpdatedEvent,
)
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    return EventBus(store=MemoryEventStore())


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def position_manager(bus: EventBus, order_store: InMemoryOrderStore) -> PaperPositionManager:
    """Create a paper position manager for testing."""
    return PaperPositionManager(bus=bus, store=order_store, starting_equity=1000.0)


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


class TestPositionUpdatedEvent:
    """Tests for PositionUpdatedEvent emission."""

    @pytest.mark.asyncio
    async def test_position_created_event_on_buy_fill(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PositionUpdatedEvent is emitted when position is created."""
        # Subscribe to position updates
        position_updates_queue = bus.subscribe(POSITION_UPDATES)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        from polytrader.events.types import OrderSubmittedEvent

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

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a fill event
            fill_event = FillEvent(
                order_id=order.order_id,
                fill_id="fill-789",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )

            # Publish fill event
            await bus.publish(FILLS, fill_event)

            # Wait for position update event (give it more time to process)
            await asyncio.sleep(0.2)

            # Check that PositionUpdatedEvent was emitted
            assert not position_updates_queue.empty(), "PositionUpdatedEvent was not emitted"
            position_event = await position_updates_queue.get()

            assert isinstance(position_event, PositionUpdatedEvent)
            assert position_event.market_slug == "test-market"
            assert position_event.outcome == "UP"
            assert position_event.net_position == 100.0
            assert position_event.size == 100.0
            assert position_event.entry_price == 0.45
            assert position_event.target_price == 0.5
            assert position_event.update_type == "created"
            assert position_event.order_id == order.order_id
            assert position_event.correlation_id == sample_intent.correlation_id
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_position_updated_event_on_additional_buy_fill(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PositionUpdatedEvent is emitted when position is updated."""
        # Subscribe to position updates
        position_updates_queue = bus.subscribe(POSITION_UPDATES)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        from polytrader.events.types import OrderSubmittedEvent

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

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # First fill - creates position
            fill_event1 = FillEvent(
                order_id=order.order_id,
                fill_id="fill-789",
                size=50.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, fill_event1)
            await asyncio.sleep(0.3)

            # Verify position was created
            positions = position_manager.get_positions()
            assert positions is not None
            assert ("test-market", "UP") in positions, "Position was not created after first fill"

            # Clear the queue
            while not position_updates_queue.empty():
                await position_updates_queue.get()

            # Second fill - updates position
            fill_event2 = FillEvent(
                order_id=order.order_id,
                fill_id="fill-790",
                size=50.0,
                price=0.46,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, fill_event2)
            await asyncio.sleep(0.3)

            # Check that PositionUpdatedEvent was emitted with update_type="updated"
            assert not position_updates_queue.empty(), "PositionUpdatedEvent was not emitted"
            position_event = await position_updates_queue.get()

            assert isinstance(position_event, PositionUpdatedEvent)
            assert position_event.update_type == "updated", (
                f"Expected 'updated', got '{position_event.update_type}'"
            )
            assert position_event.net_position == 100.0
            assert position_event.size == 100.0
            # Average entry price should be (0.45 * 50 + 0.46 * 50) / 100 = 0.455
            assert position_event.entry_price == pytest.approx(0.455)
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_position_reduced_event_on_partial_sell_fill(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PositionUpdatedEvent is emitted when position is reduced."""
        # Subscribe to position updates
        position_updates_queue = bus.subscribe(POSITION_UPDATES)

        # Create a BUY order
        buy_order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        submitted_event = OrderSubmittedEvent(
            order_id=buy_order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=buy_order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a BUY fill to establish position
            buy_fill = FillEvent(
                order_id=buy_order.order_id,
                fill_id="fill-buy",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, buy_fill)
            await asyncio.sleep(0.3)

            # Verify position was created
            positions = position_manager.get_positions()
            assert positions is not None
            assert ("test-market", "UP") in positions, "Position was not created"

            # Clear the queue
            while not position_updates_queue.empty():
                await position_updates_queue.get()

            # Create a SELL order
            sell_intent = OrderIntentEvent(
                market_slug="test-market",
                outcome="UP",
                side="SELL",
                target_price=0.5,
                limit_price=0.55,
                size=50.0,
                reason="Test sell",
                correlation_id="corr-456",
                strategy_id="simple_threshold",
            )
            sell_order = await order_store.create_order(sell_intent, "client-456")
            # Order must go through SUBMITTED before ACKED
            submitted_event = OrderSubmittedEvent(
                order_id=sell_order.order_id,
                client_order_id="client-456",
            )
            order_store.handle_order_submitted(submitted_event)
            ack_event = OrderAckEvent(
                order_id=sell_order.order_id,
                venue_order_id="venue-789",
                correlation_id=sell_intent.correlation_id,
            )
            order_store.handle_order_ack(ack_event)

            # Create a SELL fill - reduces position
            sell_fill = FillEvent(
                order_id=sell_order.order_id,
                fill_id="fill-sell",
                size=50.0,
                price=0.55,
                fee=0.01,
                correlation_id=sell_intent.correlation_id,
            )
            await bus.publish(FILLS, sell_fill)
            await asyncio.sleep(0.2)

            # Check that PositionUpdatedEvent was emitted with update_type="reduced"
            assert not position_updates_queue.empty()
            position_event = await position_updates_queue.get()

            assert isinstance(position_event, PositionUpdatedEvent)
            assert position_event.update_type == "reduced"
            assert position_event.net_position == 50.0
            assert position_event.size == 50.0
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_position_closed_event_on_full_sell_fill(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PositionUpdatedEvent is emitted when position is closed."""
        # Subscribe to position updates
        position_updates_queue = bus.subscribe(POSITION_UPDATES)

        # Create a BUY order
        buy_order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        submitted_event = OrderSubmittedEvent(
            order_id=buy_order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=buy_order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a BUY fill to establish position
            buy_fill = FillEvent(
                order_id=buy_order.order_id,
                fill_id="fill-buy",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, buy_fill)
            await asyncio.sleep(0.3)

            # Verify position was created
            positions = position_manager.get_positions()
            assert positions is not None
            assert ("test-market", "UP") in positions, "Position was not created"

            # Clear the queue
            while not position_updates_queue.empty():
                await position_updates_queue.get()

            # Create a SELL order
            sell_intent = OrderIntentEvent(
                market_slug="test-market",
                outcome="UP",
                side="SELL",
                target_price=0.5,
                limit_price=0.55,
                size=100.0,
                reason="Test sell",
                correlation_id="corr-456",
                strategy_id="simple_threshold",
            )
            sell_order = await order_store.create_order(sell_intent, "client-456")
            # Order must go through SUBMITTED before ACKED
            submitted_event = OrderSubmittedEvent(
                order_id=sell_order.order_id,
                client_order_id="client-456",
            )
            order_store.handle_order_submitted(submitted_event)
            ack_event = OrderAckEvent(
                order_id=sell_order.order_id,
                venue_order_id="venue-789",
                correlation_id=sell_intent.correlation_id,
            )
            order_store.handle_order_ack(ack_event)

            # Create a SELL fill - closes position
            sell_fill = FillEvent(
                order_id=sell_order.order_id,
                fill_id="fill-sell",
                size=100.0,
                price=0.55,
                fee=0.01,
                correlation_id=sell_intent.correlation_id,
            )
            await bus.publish(FILLS, sell_fill)
            await asyncio.sleep(0.3)

            # Check that PositionUpdatedEvent was emitted with update_type="closed"
            assert not position_updates_queue.empty(), "PositionUpdatedEvent was not emitted"
            position_event = await position_updates_queue.get()

            assert isinstance(position_event, PositionUpdatedEvent)
            assert position_event.update_type == "closed"
            assert position_event.net_position == 0.0
            assert position_event.size == 0.0
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass


class TestPnLEvent:
    """Tests for PnLEvent emission."""

    @pytest.mark.asyncio
    async def test_pnl_event_on_position_update(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PnLEvent is emitted when position is updated."""
        # Subscribe to PnL updates
        pnl_updates_queue = bus.subscribe(PNL_UPDATES)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        from polytrader.events.types import OrderSubmittedEvent

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

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a fill event
            fill_event = FillEvent(
                order_id=order.order_id,
                fill_id="fill-789",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )

            # Publish fill event
            await bus.publish(FILLS, fill_event)

            # Wait for PnL update event
            await asyncio.sleep(0.2)

            # Check that PnLEvent was emitted
            assert not pnl_updates_queue.empty()
            pnl_event = await pnl_updates_queue.get()

            assert isinstance(pnl_event, PnLEvent)
            assert pnl_event.update_reason == "position_update"
            assert pnl_event.position_count == 1
            assert pnl_event.realized_pnl == 0.0  # No closed positions yet
            # Unrealized PnL should be 0 (no market data, so uses entry price)
            assert pnl_event.unrealized_pnl == 0.0
            assert pnl_event.total_pnl == 0.0
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_pnl_event_on_price_update(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PnLEvent is emitted when market price updates."""
        # Subscribe to PnL updates
        pnl_updates_queue = bus.subscribe(PNL_UPDATES)

        # Create an order
        order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        from polytrader.events.types import OrderSubmittedEvent

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

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a fill event to establish position
            fill_event = FillEvent(
                order_id=order.order_id,
                fill_id="fill-789",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, fill_event)
            await asyncio.sleep(0.2)

            # Clear the queue
            while not pnl_updates_queue.empty():
                await pnl_updates_queue.get()

            # Publish market data event with higher price
            market_event = MarketDataEvent(
                market_slug="test-market",
                outcome="UP",
                best_bid=0.50,
                best_ask=0.52,
            )
            await bus.publish(MARKET_DATA, market_event)
            await asyncio.sleep(0.2)

            # Check that PnLEvent was emitted with update_reason="price_update"
            assert not pnl_updates_queue.empty()
            pnl_event = await pnl_updates_queue.get()

            assert isinstance(pnl_event, PnLEvent)
            assert pnl_event.update_reason == "price_update"
            assert pnl_event.position_count == 1
            # Unrealized PnL = (0.51 - 0.45) * 100 = 6.0
            assert pnl_event.unrealized_pnl == pytest.approx(6.0)
            assert pnl_event.total_pnl == pytest.approx(6.0)
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_pnl_event_includes_realized_pnl_on_close(
        self,
        bus: EventBus,
        position_manager: PaperPositionManager,
        order_store: InMemoryOrderStore,
        sample_intent: OrderIntentEvent,
    ) -> None:
        """Test that PnLEvent includes realized PnL when position is closed."""
        # Subscribe to PnL updates
        pnl_updates_queue = bus.subscribe(PNL_UPDATES)

        # Create a BUY order
        buy_order = await order_store.create_order(sample_intent, "client-123")
        # Order must go through SUBMITTED before ACKED
        submitted_event = OrderSubmittedEvent(
            order_id=buy_order.order_id,
            client_order_id="client-123",
        )
        order_store.handle_order_submitted(submitted_event)
        ack_event = OrderAckEvent(
            order_id=buy_order.order_id,
            venue_order_id="venue-456",
            correlation_id=sample_intent.correlation_id,
        )
        order_store.handle_order_ack(ack_event)

        # Start position manager
        position_task = asyncio.create_task(position_manager.run())
        # Give position manager time to start and subscribe to events
        await asyncio.sleep(0.1)

        try:
            # Create a BUY fill to establish position
            buy_fill = FillEvent(
                order_id=buy_order.order_id,
                fill_id="fill-buy",
                size=100.0,
                price=0.45,
                fee=0.01,
                correlation_id=sample_intent.correlation_id,
            )
            await bus.publish(FILLS, buy_fill)
            await asyncio.sleep(0.3)

            # Verify position was created
            positions = position_manager.get_positions()
            assert positions is not None
            assert ("test-market", "UP") in positions, "Position was not created"

            # Clear the queue
            while not pnl_updates_queue.empty():
                await pnl_updates_queue.get()

            # Create a SELL order
            sell_intent = OrderIntentEvent(
                market_slug="test-market",
                outcome="UP",
                side="SELL",
                target_price=0.5,
                limit_price=0.55,
                size=100.0,
                reason="Test sell",
                correlation_id="corr-456",
                strategy_id="simple_threshold",
            )
            sell_order = await order_store.create_order(sell_intent, "client-456")
            # Order must go through SUBMITTED before ACKED
            submitted_event = OrderSubmittedEvent(
                order_id=sell_order.order_id,
                client_order_id="client-456",
            )
            order_store.handle_order_submitted(submitted_event)
            ack_event = OrderAckEvent(
                order_id=sell_order.order_id,
                venue_order_id="venue-789",
                correlation_id=sell_intent.correlation_id,
            )
            order_store.handle_order_ack(ack_event)

            # Create a SELL fill - closes position
            sell_fill = FillEvent(
                order_id=sell_order.order_id,
                fill_id="fill-sell",
                size=100.0,
                price=0.55,
                fee=0.01,
                correlation_id=sell_intent.correlation_id,
            )
            await bus.publish(FILLS, sell_fill)
            await asyncio.sleep(0.3)

            # Check that PnLEvent was emitted with realized PnL
            # We need to wait a bit for the performance metrics to update
            await asyncio.sleep(0.3)

            # Get the last PnL event (should be after position close)
            pnl_events = []
            while not pnl_updates_queue.empty():
                pnl_events.append(await pnl_updates_queue.get())

            # Should have at least one PnL event
            assert len(pnl_events) > 0

            # The last event should be from position update
            last_pnl_event = pnl_events[-1]
            assert isinstance(last_pnl_event, PnLEvent)
            assert last_pnl_event.update_reason == "position_update"
            assert last_pnl_event.position_count == 0  # Position closed
        finally:
            position_manager.stop()
            position_task.cancel()
            try:
                await position_task
            except asyncio.CancelledError:
                pass
