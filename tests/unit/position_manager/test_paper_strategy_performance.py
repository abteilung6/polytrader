"""Tests for per-strategy performance summaries in PaperPositionManager."""

import asyncio

import pytest

from polytrader.events import FILLS, MARKET_DATA, EventBus
from polytrader.events.types import FillEvent, MarketDataEvent, OrderIntentEvent
from polytrader.oms.store import InMemoryOrderStore
from polytrader.position_manager.paper import PaperPositionManager


@pytest.fixture
def bus() -> EventBus:
    """Create an event bus for testing."""
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
async def test_strategy_performance_summary_tracks_realized_and_unrealized(
    bus: EventBus,
    order_store: InMemoryOrderStore,
    position_manager: PaperPositionManager,
) -> None:
    """Ensure per-strategy summary includes realized and unrealized PnL."""
    manager_task = asyncio.create_task(position_manager.run())
    await asyncio.sleep(0.05)

    try:
        # Open position (BUY)
        buy_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="BUY",
            size=10.0,
            target_price=0.50,
            limit_price=0.40,
            reason="Test buy",
            strategy_id="strategy-1",
            ttl_s=60.0,
        )
        buy_order = await order_store.create_order(buy_intent, "client-buy")
        buy_fill = FillEvent(
            order_id=buy_order.order_id,
            fill_id="fill-buy",
            size=10.0,
            price=0.40,
            fee=0.0,
            correlation_id=buy_intent.correlation_id,
        )
        await bus.publish(FILLS, buy_fill)

        # Wait for position to be created
        for _ in range(10):
            await asyncio.sleep(0.05)
            positions = position_manager.get_positions()
            if positions and ("test-market", "UP") in positions:
                break

        # Update market price for unrealized PnL
        market_event = MarketDataEvent(
            market_slug="test-market",
            outcome="UP",
            best_bid=0.49,
            best_ask=0.51,
        )
        await bus.publish(MARKET_DATA, market_event)

        # Wait for market data to be processed
        for _ in range(10):
            await asyncio.sleep(0.05)
            if ("test-market", "UP") in position_manager._latest_prices:
                break

        summary = position_manager.get_strategy_performance_summary("strategy-1")
        assert summary["total_realized_pnl"] == pytest.approx(0.0, abs=0.01)
        assert summary["unrealized_pnl"] == pytest.approx(1.0, abs=0.01)
        assert summary["total_pnl"] == pytest.approx(1.0, abs=0.01)

        # Close position (SELL)
        sell_intent = OrderIntentEvent(
            market_slug="test-market",
            outcome="UP",
            side="SELL",
            size=10.0,
            target_price=0.60,
            limit_price=0.60,
            reason="Test sell",
            strategy_id="strategy-1",
            ttl_s=60.0,
        )
        sell_order = await order_store.create_order(sell_intent, "client-sell")
        sell_fill = FillEvent(
            order_id=sell_order.order_id,
            fill_id="fill-sell",
            size=10.0,
            price=0.60,
            fee=0.0,
            correlation_id=sell_intent.correlation_id,
        )
        await bus.publish(FILLS, sell_fill)

        # Wait for position to be closed
        for _ in range(10):
            await asyncio.sleep(0.05)
            positions = position_manager.get_positions()
            if positions is not None and ("test-market", "UP") not in positions:
                break

        summary_after = position_manager.get_strategy_performance_summary("strategy-1")
        assert summary_after["total_realized_pnl"] == pytest.approx(2.0, abs=0.01)
        assert summary_after["unrealized_pnl"] == pytest.approx(0.0, abs=0.01)
        assert summary_after["total_pnl"] == pytest.approx(2.0, abs=0.01)

    finally:
        position_manager.stop()
        manager_task.cancel()
        try:
            await manager_task
        except asyncio.CancelledError:
            pass
