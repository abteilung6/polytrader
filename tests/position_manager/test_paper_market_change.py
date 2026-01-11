"""Tests for automatic position closure on market expiration.

Tests that PaperPositionManager automatically closes positions when
MarketChangeEvent occurs (market expiration/transition).
"""

import asyncio

import pytest

from polytrader.events import FILLS, MARKET_CHANGE, MARKET_DATA, EventBus
from polytrader.events.types import FillEvent, MarketChangeEvent, MarketDataEvent, OrderIntentEvent
from polytrader.oms.models import OrderState
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def order_store(bus: EventBus) -> InMemoryOrderStore:
    return InMemoryOrderStore(bus)


@pytest.fixture
def position_manager(bus: EventBus, order_store: InMemoryOrderStore) -> PaperPositionManager:
    return PaperPositionManager(bus=bus, store=order_store, starting_equity=1000.0)


@pytest.mark.asyncio
async def test_market_change_closes_positions(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test that positions are closed when market changes."""
    # Start position manager
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)  # Give manager time to subscribe

    try:
        # Create order and fill for market-1
        intent = OrderIntentEvent(
            market_slug="market-1",
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

        # Publish fill event
        await bus.publish(FILLS, fill_event)
        await asyncio.sleep(0.1)

        # Verify position exists
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") in positions, "Position should exist after fill"

        # Add market data for both outcomes to determine settlement
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.60,
                best_ask=0.65,
            ),
        )
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="DOWN",
                best_bid=0.35,
                best_ask=0.40,
            ),
        )
        await asyncio.sleep(0.1)

        # Publish market change event (market-1 → market-2)
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)  # Give time for processing

        # Verify position is closed
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") not in positions, "Position should be closed after market change"

        # Verify position was recorded in outcome tracker
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1, "Should have 1 closed position"
        assert closed_positions[0].market_slug == "market-1"
        assert closed_positions[0].outcome == "UP"
        assert closed_positions[0].exit_price == 1.0, "UP should win (price 0.625 > 0.375)"
        assert closed_positions[0].pnl > 0, "Should have positive P&L (entry 0.30, exit 1.0)"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_market_change_no_positions(
    bus: EventBus,
    position_manager: PaperPositionManager,
) -> None:
    """Test that market change with no positions doesn't error."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Publish market change with no positions
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.1)

        # Should not error
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert len(positions) == 0, "Should have no positions"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_market_change_initial_market(
    bus: EventBus,
    position_manager: PaperPositionManager,
) -> None:
    """Test that initial market (old_market=None) doesn't close positions."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Publish market change with no old_market (initial market)
        market_change = MarketChangeEvent(
            old_market=None,
            new_market="market-1",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.1)

        # Should not error and should not close anything
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert len(positions) == 0, "Should have no positions"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_settlement_price_up_wins(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test settlement price when UP wins (UP price > DOWN price)."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create position
        intent = OrderIntentEvent(
            market_slug="market-1",
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
        await bus.publish(FILLS, fill_event)
        await asyncio.sleep(0.1)

        # Add market data: UP price (0.70) > DOWN price (0.30)
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.69,
                best_ask=0.71,
            ),
        )
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="DOWN",
                best_bid=0.29,
                best_ask=0.31,
            ),
        )
        await asyncio.sleep(0.1)

        # Trigger market change
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify UP position settled at 1.0 (wins)
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].exit_price == 1.0, "UP should win and settle at 1.0"
        assert closed_positions[0].pnl == pytest.approx(7.0, abs=0.01), (
            "P&L should be (1.0 - 0.30) * 10.0 = 7.0"
        )

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_settlement_price_down_wins(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test settlement price when DOWN wins (DOWN price > UP price)."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create DOWN position
        intent = OrderIntentEvent(
            market_slug="market-1",
            outcome="DOWN",
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
        await bus.publish(FILLS, fill_event)
        await asyncio.sleep(0.1)

        # Add market data: DOWN price (0.70) > UP price (0.30)
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.29,
                best_ask=0.31,
            ),
        )
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="DOWN",
                best_bid=0.69,
                best_ask=0.71,
            ),
        )
        await asyncio.sleep(0.1)

        # Trigger market change
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify DOWN position settled at 1.0 (wins)
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].exit_price == 1.0, "DOWN should win and settle at 1.0"
        assert closed_positions[0].pnl == pytest.approx(7.0, abs=0.01), (
            "P&L should be (1.0 - 0.30) * 10.0 = 7.0"
        )

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_settlement_price_no_market_data_uses_entry_price(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test settlement price fallback to entry price when no market data."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create position
        intent = OrderIntentEvent(
            market_slug="market-1",
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
        await bus.publish(FILLS, fill_event)
        await asyncio.sleep(0.1)

        # Trigger market change WITHOUT market data
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify position settled at entry price (breakeven)
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].exit_price == 0.30, "Should use entry price as fallback"
        assert closed_positions[0].pnl == 0.0, "Should be breakeven (entry = exit)"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_settlement_price_single_outcome_price(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test settlement price when only one outcome has market data."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create UP position
        intent = OrderIntentEvent(
            market_slug="market-1",
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
        await bus.publish(FILLS, fill_event)
        await asyncio.sleep(0.1)

        # Add market data only for UP (price > 0.5, so should win)
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.69,
                best_ask=0.71,
            ),
        )
        await asyncio.sleep(0.1)

        # Trigger market change
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify UP position settled at 1.0 (price > 0.5)
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].exit_price == 1.0, "UP price > 0.5, should win"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_market_change_multiple_positions_same_market(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test that multiple positions in same market are all closed."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create UP position
        intent_up = OrderIntentEvent(
            market_slug="market-1",
            outcome="UP",
            side="BUY",
            size=10.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test UP",
            ttl_s=60.0,
        )
        order_up = await order_store.create_order(intent_up, "client-1")
        order_up.state = OrderState.FILLED
        order_store.update_order(order_up)

        fill_up = FillEvent(
            order_id=order_up.order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-1",
            correlation_id=intent_up.correlation_id,
        )
        await bus.publish(FILLS, fill_up)
        await asyncio.sleep(0.1)

        # Create DOWN position
        intent_down = OrderIntentEvent(
            market_slug="market-1",
            outcome="DOWN",
            side="BUY",
            size=5.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test DOWN",
            ttl_s=60.0,
        )
        order_down = await order_store.create_order(intent_down, "client-2")
        order_down.state = OrderState.FILLED
        order_store.update_order(order_down)

        fill_down = FillEvent(
            order_id=order_down.order_id,
            fill_id="fill-2",
            size=5.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-2",
            correlation_id=intent_down.correlation_id,
        )
        await bus.publish(FILLS, fill_down)
        await asyncio.sleep(0.1)

        # Verify both positions exist
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") in positions
        assert ("market-1", "DOWN") in positions

        # Add market data: UP wins
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.69,
                best_ask=0.71,
            ),
        )
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="DOWN",
                best_bid=0.29,
                best_ask=0.31,
            ),
        )
        await asyncio.sleep(0.1)

        # Trigger market change
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-2",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify both positions are closed
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") not in positions
        assert ("market-1", "DOWN") not in positions

        # Verify both recorded in outcome tracker
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 2

        # UP should win (exit_price = 1.0), DOWN should lose (exit_price = 0.0)
        up_closed = next((p for p in closed_positions if p.outcome == "UP"), None)
        down_closed = next((p for p in closed_positions if p.outcome == "DOWN"), None)

        assert up_closed is not None
        assert down_closed is not None
        assert up_closed.exit_price == 1.0, "UP should win"
        assert down_closed.exit_price == 0.0, "DOWN should lose"
        assert up_closed.pnl == pytest.approx(7.0, abs=0.01), "UP P&L: (1.0 - 0.30) * 10.0"
        assert down_closed.pnl == pytest.approx(-1.5, abs=0.01), "DOWN P&L: (0.0 - 0.30) * 5.0"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_market_change_only_closes_old_market_positions(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Test that only positions in old_market are closed, not other markets."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.1)

    try:
        # Create position in market-1
        intent1 = OrderIntentEvent(
            market_slug="market-1",
            outcome="UP",
            side="BUY",
            size=10.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test",
            ttl_s=60.0,
        )
        order1 = await order_store.create_order(intent1, "client-1")
        order1.state = OrderState.FILLED
        order_store.update_order(order1)

        fill1 = FillEvent(
            order_id=order1.order_id,
            fill_id="fill-1",
            size=10.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-1",
            correlation_id=intent1.correlation_id,
        )
        await bus.publish(FILLS, fill1)
        await asyncio.sleep(0.1)

        # Create position in market-2 (different market)
        intent2 = OrderIntentEvent(
            market_slug="market-2",
            outcome="UP",
            side="BUY",
            size=5.0,
            target_price=0.50,
            limit_price=0.30,
            reason="Test",
            ttl_s=60.0,
        )
        order2 = await order_store.create_order(intent2, "client-2")
        order2.state = OrderState.FILLED
        order_store.update_order(order2)

        fill2 = FillEvent(
            order_id=order2.order_id,
            fill_id="fill-2",
            size=5.0,
            price=0.30,
            fee=0.0,
            venue_fill_id="venue-2",
            correlation_id=intent2.correlation_id,
        )
        await bus.publish(FILLS, fill2)
        await asyncio.sleep(0.1)

        # Verify both positions exist
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") in positions
        assert ("market-2", "UP") in positions

        # Add market data for market-1
        await bus.publish(
            MARKET_DATA,
            MarketDataEvent(
                market_slug="market-1",
                outcome="UP",
                best_bid=0.69,
                best_ask=0.71,
            ),
        )
        await asyncio.sleep(0.1)

        # Trigger market change: market-1 → market-3
        market_change = MarketChangeEvent(
            old_market="market-1",
            new_market="market-3",
        )
        await bus.publish(MARKET_CHANGE, market_change)
        await asyncio.sleep(0.2)

        # Verify only market-1 position is closed
        positions = position_manager.get_positions()
        assert positions is not None, "Positions dict should exist"
        assert ("market-1", "UP") not in positions, "market-1 position should be closed"
        assert ("market-2", "UP") in positions, "market-2 position should remain open"

        # Verify only market-1 recorded in outcome tracker
        tracker = position_manager.get_outcome_tracker()
        closed_positions = tracker.get_closed_positions()
        assert len(closed_positions) == 1
        assert closed_positions[0].market_slug == "market-1"

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass
