"""Tests for PaperPositionManager unrealized P&L calculation.

Tests that unrealized P&L is correctly calculated using current market prices
from MarketDataEvent subscriptions.
"""

import asyncio

import pytest

from polytrader.events import FILLS, MARKET_DATA, EventBus
from polytrader.events.types import FillEvent, MarketDataEvent, OrderIntentEvent
from polytrader.oms.models import OrderState
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
    from polytrader.events.bus import EventBus

    return EventBus()


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    """Create an order store for testing."""
    return InMemoryOrderStore(bus)


@pytest.fixture
def position_manager(bus: EventBus, order_store: InMemoryOrderStore) -> PaperPositionManager:
    """Create a paper position manager for testing."""
    return PaperPositionManager(bus=bus, store=order_store, starting_equity=1000.0)


@pytest.mark.asyncio
async def test_unrealized_pnl_with_market_data(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test that unrealized P&L uses current market prices from MarketDataEvent."""
    # Start position manager
    manager_task = asyncio.create_task(position_manager.run())
    # Give position manager time to start and subscribe to queues
    await asyncio.sleep(0.1)

    try:
        # Create an order intent and order
        intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=10.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test",
            ttl_s=60.0,
        )
        order = await order_store.create_order(intent, "client-1")
        # Manually update order to FILLED state for testing
        order.state = OrderState.FILLED
        order_store.update_order(order)

        # Verify order is in store
        stored_order = order_store.get_order(order.order_id)
        assert stored_order is not None, f"Order {order.order_id} should be in store"
        assert stored_order.order_id == order.order_id

        # Create a fill event at entry price 0.30
        fill_event = FillEvent(
            order_id=order.order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-1",
            correlation_id=intent.correlation_id,
        )

        # Publish fill event and wait for processing
        await bus.publish(FILLS, fill_event)
        # Wait for fill to be processed - try multiple times
        for _ in range(10):
            await asyncio.sleep(0.1)
            positions = position_manager.get_positions()
            if positions and ("test-market", "UP") in positions:
                break

        # Verify position was created
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("test-market", "UP") in positions, (
            f"Position should exist after fill. Got positions: {list(positions.keys())}"
        )

        # Initially, no market data - unrealized P&L should be 0 (uses entry price)
        unrealized = position_manager.calculate_unrealized_pnl()
        assert unrealized == 0.0, "Unrealized P&L should be 0 when no market data available"

        # Publish market data with current price 0.40 (price went up)
        market_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.39,
            best_ask=0.41,
        )
        await bus.publish(MARKET_DATA, market_event)
        # Wait for market data to be processed
        for _ in range(10):
            await asyncio.sleep(0.1)
            if ("test-market", "UP") in position_manager._latest_prices:
                break

        # Verify market price was updated
        assert ("test-market", "UP") in position_manager._latest_prices
        latest_price = position_manager._latest_prices[("test-market", "UP")]
        assert latest_price == pytest.approx(0.40, abs=0.01)

        # Now unrealized P&L should be positive: (0.40 - 0.30) * 10.0 = 1.0
        unrealized = position_manager.calculate_unrealized_pnl()
        expected_pnl = (0.40 - 0.30) * 10.0  # (current_mid - entry_price) * size
        assert unrealized == pytest.approx(expected_pnl, abs=0.01), (
            f"Unrealized P&L should be {expected_pnl}, got {unrealized}"
        )

        # Update market data with lower price 0.25 (price went down)
        market_event2 = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.24,
            best_ask=0.26,
        )
        await bus.publish(MARKET_DATA, market_event2)
        # Wait for market data to be processed
        for _ in range(10):
            await asyncio.sleep(0.1)
            if ("test-market", "UP") in position_manager._latest_prices:
                latest_price = position_manager._latest_prices[("test-market", "UP")]
                if latest_price == pytest.approx(0.25, abs=0.01):
                    break

        # Now unrealized P&L should be negative: (0.25 - 0.30) * 10.0 = -0.5
        unrealized = position_manager.calculate_unrealized_pnl()
        expected_pnl = (0.25 - 0.30) * 10.0
        assert unrealized == pytest.approx(expected_pnl, abs=0.01), (
            f"Unrealized P&L should be {expected_pnl}, got {unrealized}"
        )

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_unrealized_pnl_with_provided_prices(
    position_manager: PaperPositionManager,
) -> None:
    """Test that provided current_prices override tracked market prices."""
    # Manually create a position (simulating a fill)
    from polytrader.types import Position

    position = Position(
        market_slug="test-market",
        outcome="UP",
        size=10.0,
        entry_price=0.30,
        target_price=0.50,
        entry_time=1000.0,
    )
    position_manager._positions[("test-market", "UP")] = position

    # Set tracked market price to 0.40
    position_manager._latest_prices[("test-market", "UP")] = 0.40

    # Without provided prices, should use tracked price
    unrealized = position_manager.calculate_unrealized_pnl()
    expected = (0.40 - 0.30) * 10.0
    assert unrealized == pytest.approx(expected, abs=0.01)

    # With provided prices, should override tracked price
    from polytrader.types import Outcome

    provided_prices: dict[tuple[str, Outcome], float] = {("test-market", "UP"): 0.45}
    unrealized = position_manager.calculate_unrealized_pnl(current_prices=provided_prices)
    expected = (0.45 - 0.30) * 10.0
    assert unrealized == pytest.approx(expected, abs=0.01)


@pytest.mark.asyncio
async def test_unrealized_pnl_multiple_positions(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test unrealized P&L calculation with multiple positions."""
    # Start position manager
    manager_task = asyncio.create_task(position_manager.run())
    # Give position manager time to start and subscribe to queues
    await asyncio.sleep(0.1)

    try:
        # Create two order intents and orders
        intent1 = OrderIntentEvent(
            market_slug="market-1",
            outcome="UP",
            side="BUY",
            size=10.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test 1",
            ttl_s=60.0,
        )
        intent2 = OrderIntentEvent(
            market_slug="market-2",
            outcome="DOWN",
            side="BUY",
            size=5.0,
            target_price=0.70,
            limit_price=0.60,
            reason="Test 2",
            ttl_s=60.0,
        )

        order1 = await order_store.create_order(intent1, "client-1")
        order1.state = OrderState.FILLED
        order_store.update_order(order1)

        order2 = await order_store.create_order(intent2, "client-2")
        order2.state = OrderState.FILLED
        order_store.update_order(order2)

        # Create fills
        fill1 = FillEvent(
            order_id=order1.order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-1",
            correlation_id=intent1.correlation_id,
        )
        fill2 = FillEvent(
            order_id=order2.order_id,
            fill_id="fill-2",
            size=5.0,
            price=0.60,
            fee=0.0,
            venue_fill_id="venue-2",
            correlation_id=intent2.correlation_id,
        )

        await bus.publish(FILLS, fill1)
        await bus.publish(FILLS, fill2)
        await asyncio.sleep(0.1)

        # Publish market data for both positions
        market1 = MarketDataEvent(
            market_slug="market-1",
            outcome="UP",
            best_bid=0.39,
            best_ask=0.41,
        )
        market2 = MarketDataEvent(
            market_slug="market-2",
            outcome="DOWN",
            best_bid=0.64,
            best_ask=0.66,
        )

        await bus.publish(MARKET_DATA, market1)
        await bus.publish(MARKET_DATA, market2)
        # Wait for market data to be processed
        for _ in range(10):
            await asyncio.sleep(0.1)
            if ("market-1", "UP") in position_manager._latest_prices and (
                "market-2",
                "DOWN",
            ) in position_manager._latest_prices:
                break

        # Calculate total unrealized P&L
        unrealized = position_manager.calculate_unrealized_pnl()
        # Position 1: (0.40 - 0.30) * 10.0 = 1.0
        # Position 2: (0.65 - 0.60) * 5.0 = 0.25
        # Total: 1.25
        expected = (0.40 - 0.30) * 10.0 + (0.65 - 0.60) * 5.0
        assert unrealized == pytest.approx(expected, abs=0.01), (
            f"Total unrealized P&L should be {expected}, got {unrealized}"
        )

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_unrealized_pnl_no_positions(position_manager: PaperPositionManager) -> None:
    """Test that unrealized P&L is 0 when there are no positions."""
    unrealized = position_manager.calculate_unrealized_pnl()
    assert unrealized == 0.0, "Unrealized P&L should be 0 with no positions"


@pytest.mark.asyncio
async def test_unrealized_pnl_direct_handler(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test unrealized P&L by directly calling handlers (bypasses async queue)."""
    # Create order and fill event
    intent = OrderIntentEvent(
        market_slug="test-market",
        outcome="UP",
        side="BUY",
        size=10.0,
        target_price=0.50,
        limit_price=0.30,
        reason="Test",
        ttl_s=60.0,
    )
    order = await order_store.create_order(intent, "client-1")
    order.state = OrderState.FILLED
    order_store.update_order(order)

    fill_event = FillEvent(
        order_id=order.order_id,
        fill_id="fill-1",
        size=10.0,
        price=0.30,
        fee=0.0,
        venue_fill_id="venue-1",
        correlation_id=intent.correlation_id,
    )

    # Directly call handler (bypassing async queue)
    await position_manager._handle_fill(fill_event)

    # Verify position was created
    positions = position_manager.get_positions()
    assert positions is not None
    assert ("test-market", "UP") in positions

    # Initially no market data - should be 0
    unrealized = position_manager.calculate_unrealized_pnl()
    assert unrealized == 0.0

    # Manually set market price
    market_event = MarketDataEvent(
        market_slug="test-market",
        outcome="UP",
        best_bid=0.39,
        best_ask=0.41,
    )
    position_manager._handle_market_data(market_event)

    # Now should show unrealized P&L
    unrealized = position_manager.calculate_unrealized_pnl()
    expected = (0.40 - 0.30) * 10.0
    assert unrealized == pytest.approx(expected, abs=0.01)
